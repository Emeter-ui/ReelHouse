"""fzmovies-based h264 fallback resolver.

Some MovieBox titles only ship HEVC, which iOS Safari can't decode. fzmovies
hosts the same titles with browser-friendly h264 streams (480p .mp4 directly,
720p .mkv with h264 inside). This module resolves a TMDB-style (title, year)
to a final fzmovies URL the player can consume.

Flow: Search -> Navigate -> DownloadLinks -> Download.last_url. The whole
fzmovies-api SDK is sync (built on `requests`), so we run each step in a
thread to keep the FastAPI loop free, and we serialize requests with a lock
because the SDK uses a shared module-level `requests.Session`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fzmovies_api import DownloadLinks, Download, Navigate, Search
from fzmovies_api.models import FileMetadata

from .matching import Candidate, best_match

logger = logging.getLogger(__name__)

# fzmovies-api has a single module-level `requests.Session` so concurrent
# resolutions would race on cookies and the per-download Range header. Cheap
# fix: serialize. We can revisit if latency becomes a bottleneck.
_lock = asyncio.Lock()

_QUALITY_INDEX_480P = 0
_QUALITY_INDEX_720P = 1

# Resolution latency is 7-10s and the final URL hostname is per-request, so
# cache for long enough to absorb pause/refresh within a session. Keep it
# below the URL's likely TTL (we treat it as ~15min based on signed-URL
# heuristics — re-resolve if a stream fails).
_CACHE_TTL = 10 * 60
_cache: dict[tuple[str, int | None], tuple[float, dict[str, Any] | None]] = {}


def _cache_get(key: tuple[str, int | None]) -> dict[str, Any] | None | _Sentinel:
    hit = _cache.get(key)
    if hit is None:
        return _MISS
    expires_at, value = hit
    if time.monotonic() >= expires_at:
        _cache.pop(key, None)
        return _MISS
    return value


def _cache_set(key: tuple[str, int | None], value: dict[str, Any] | None) -> None:
    _cache[key] = (time.monotonic() + _CACHE_TTL, value)


class _Sentinel: ...
_MISS = _Sentinel()


def _to_candidates(movies: list[Any]) -> list[Candidate]:
    out: list[Candidate] = []
    for m in movies:
        out.append(Candidate(
            # `subject_id` here just needs a unique key per candidate. We use
            # the URL — that's what we'll need to navigate to anyway.
            subject_id=str(m.url),
            title=m.title,
            year=int(m.year) if m.year else None,
        ))
    return out


def _pick_movie_file(files: list[FileMetadata]) -> FileMetadata | None:
    """Return the 480p .mp4 entry. fzmovies indexes files in (480p, 720p)
    order, but we still verify the title to avoid grabbing a 720p mkv if
    the listing shape changes."""
    if not files:
        return None
    if len(files) > _QUALITY_INDEX_480P:
        f = files[_QUALITY_INDEX_480P]
        if "480p" in f.title.lower() and ".mp4" in f.title.lower():
            return f
    # Fallback: scan for any 480p mp4 entry.
    for f in files:
        t = f.title.lower()
        if "480p" in t and ".mp4" in t:
            return f
    return None


def _resolve_blocking(title: str, year: int | None) -> dict[str, Any] | None:
    """Synchronous resolution; runs entirely in a worker thread."""
    t0 = time.perf_counter()

    # 1) Search
    movies = Search(query=title, searchby="Name").results.movies
    t_search = time.perf_counter() - t0
    if not movies:
        logger.info("[fzmovies] no search hits for %r (search=%.0fms)", title, t_search * 1000)
        return None

    candidates = _to_candidates(movies)
    match = best_match(title, year, candidates)
    if match is None:
        logger.info(
            "[fzmovies] no acceptable match for %r (year=%s) among %d candidates",
            title, year, len(candidates),
        )
        return None

    target_movie = next((m for m in movies if str(m.url) == match.subject_id), None)
    if target_movie is None:
        logger.warning("[fzmovies] matched candidate not found in original list")
        return None

    # 2) Movie page -> file list
    t1 = time.perf_counter()
    files = Navigate(target_movie).results.files
    t_nav = time.perf_counter() - t1
    movie_file = _pick_movie_file(files)
    if movie_file is None:
        logger.info(
            "[fzmovies] no 480p mp4 for %r (got %d files, nav=%.0fms)",
            target_movie.title, len(files), t_nav * 1000,
        )
        return None

    # 3) Download links page (contains mirror list)
    t2 = time.perf_counter()
    download_movie = DownloadLinks(movie_file).results
    t_links = time.perf_counter() - t2
    if not download_movie.links:
        logger.info("[fzmovies] no mirrors for %r", target_movie.title)
        return None

    # 4) Walk dlink.php to get the final CDN URL.
    t3 = time.perf_counter()
    final_url = Download(download_movie.links[0]).last_url
    t_final = time.perf_counter() - t3
    if not final_url:
        return None

    logger.info(
        "[fzmovies] %r resolved (search=%.0fms nav=%.0fms links=%.0fms final=%.0fms)",
        target_movie.title,
        t_search * 1000, t_nav * 1000, t_links * 1000, t_final * 1000,
    )

    return {
        "url": final_url,
        "filename": download_movie.filename,
        "size_label": download_movie.size,
        "title": target_movie.title,
        "year": target_movie.year,
    }


async def resolve_h264(title: str, year: int | None) -> dict[str, Any] | None:
    """Resolve a (title, year) to a 480p h264 mp4 URL via fzmovies, or None.

    Returns a dict shaped to slot directly into the player `qualities` list:
        {"resolution": "480p", "size_bytes": int, "url": str,
         "codec": "h264", "format": "mp4", "source": "fzmovies"}
    or None if nothing playable was found.
    """
    if not title:
        return None

    key = (title.casefold(), year)
    cached = _cache_get(key)
    if cached is not _MISS:
        if cached is not None:
            logger.info("[fzmovies] cache hit for %r (year=%s)", title, year)
        return cached  # may be None — we cache negatives too, briefly

    async with _lock:
        # Re-check after acquiring the lock — another waiter may have populated
        # the cache while we were queued.
        cached = _cache_get(key)
        if cached is not _MISS:
            return cached

        t0 = time.perf_counter()
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(_resolve_blocking, title, year),
                timeout=35.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[fzmovies] timeout resolving %r", title)
            data = None
        except Exception as e:
            logger.warning(
                "[fzmovies] error resolving %r: %s: %s",
                title, type(e).__name__, e,
            )
            data = None
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if data is None:
            _cache_set(key, None)
            logger.info("[fzmovies] miss for %r (year=%s) in %.0fms", title, year, elapsed_ms)
            return None

        # Best-effort size in bytes from human-readable size string.
        size_bytes = _parse_size_bytes(data.get("size_label") or "")

        result = {
            "resolution": "480p",
            "size_bytes": size_bytes,
            "url": data["url"],
            "codec": "h264",
            "format": "mp4",
            "source": "fzmovies",
        }
        _cache_set(key, result)
        logger.info(
            "[fzmovies] hit %r -> %s (%.0fms)",
            title, data["filename"], elapsed_ms,
        )
        return result


def _parse_size_bytes(label: str) -> int:
    """Convert "272 MB" / "1.04 GB" to bytes; return 0 on failure."""
    if not label:
        return 0
    parts = label.strip().split()
    if len(parts) != 2:
        return 0
    try:
        n = float(parts[0])
    except ValueError:
        return 0
    unit = parts[1].upper()
    multiplier = {"KB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000}.get(unit, 0)
    return int(n * multiplier)
