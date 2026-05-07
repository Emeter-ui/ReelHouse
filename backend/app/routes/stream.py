"""Resolve a TMDB title to a moviebox stream URL + qualities + captions.

Hits MovieBox's web `/subject/play` endpoint (the same one the official h5
player and third-party sites like mymuvies use). Avoids `/subject-api/resource`
because that's the mobile download endpoint — its URLs are HEVC-dominant and
not designed for browser `<video>`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession
from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.constants import ResolutionType
from moviebox_api.v3.core import DownloadableVideoFilesDetail, ItemDetails, Search
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.models.downloadables import VideoFileMetadata

from ..cache import TTLCache
from ..matching import Candidate, best_match

logger = logging.getLogger(__name__)

# Impersonate real Chrome's TLS fingerprint so MovieBox doesn't flag the
# request as bot traffic from the (datacenter) backend host.
_IMPERSONATE = "chrome124"

router = APIRouter()

# Play URLs are short-lived signed CDN links. Cache long enough to absorb
# pause/refresh within a session, short enough that we re-sign before the
# upstream signature expires.
_cache = TTLCache(maxsize=512, ttl_seconds=3 * 60)

_PLAY_DOMAIN_FALLBACK = "https://h5.aoneroom.com"
_PLAY_DOMAIN_DISCOVERY = (
    "https://h5-api.aoneroom.com/wefeed-h5api-bff/media-player/get-domain"
)
_PLAY_PATH = "/wefeed-h5api-bff/subject/play"
_DOWNLOAD_PATH = "/wefeed-h5api-bff/subject/download"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_X_CLIENT_INFO = '{"timezone":"Africa/Nairobi"}'

# A UUID-shaped cookie satisfies MovieBox's anti-scrape session check.
# Value doesn't have to be registered — just present and well-formed.
_SESSION_COOKIES = {"uuid": "d8c3539e-2e46-4000-af20-7046a856e30a"}


def _cache_key(
    source_id: int | str | None,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
) -> str:
    # Anime callers (AniList) have no tmdb_id — fall back to title+year so
    # cache hits still happen across repeated lookups.
    base = source_id if source_id is not None else f"{title.casefold()}|{year or ''}"
    return f"{base}:{season or ''}:{episode or ''}"


def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[-1] if parts else None


async def _search_candidates(
    client: MovieBoxHttpClient, query: str, subject_type: SubjectType
) -> list[Candidate]:
    search = Search(client_session=client, query=query, subject_type=subject_type)
    try:
        result = await search.get_content_model()
    except Exception:
        return []

    out: list[Candidate] = []
    for item in result.items:
        if not item.has_resource:
            continue
        year = item.release_date.year if item.release_date else None
        out.append(
            Candidate(
                subject_id=item.subject_id,
                title=item.title,
                year=year,
                detail_path=_slug_from_url(
                    str(item.detail_url) if item.detail_url else None
                ),
            )
        )
    return out


async def _resolve_target(
    client: MovieBoxHttpClient, subject_id: str, fallback_detail_path: str | None
) -> tuple[str, str | None]:
    # MovieBox indexes localized dubs (Hindi, Tamil, etc.) under separate
    # subject_ids and often ranks them ahead of the English original in search.
    # Redirect to the Original dub and use its canonical detail_path slug for
    # the play Referer.
    try:
        details = await ItemDetails(client_session=client).get_content_model(subject_id)
    except Exception:
        return subject_id, fallback_detail_path

    target_id = subject_id
    for dub in details.dubs:
        if dub.original:
            target_id = dub.subject_id
            break

    if target_id != subject_id:
        try:
            details = await ItemDetails(client_session=client).get_content_model(target_id)
        except Exception:
            return target_id, fallback_detail_path

    target_slug = _slug_from_url(
        str(details.detail_url) if details.detail_url else None
    )
    return target_id, target_slug or fallback_detail_path


async def _resolve_play_domain(client: AsyncSession) -> str:
    try:
        r = await client.get(
            _PLAY_DOMAIN_DISCOVERY,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "application/json",
                "X-Client-Info": _X_CLIENT_INFO,
                "X-Client-Type": "h5",
            },
            timeout=10,
        )
        if r.status_code == 200:
            domain = (r.json().get("data") or _PLAY_DOMAIN_FALLBACK).rstrip("/")
            if domain.startswith("http"):
                return domain
    except Exception:
        pass
    return _PLAY_DOMAIN_FALLBACK


async def _fetch_play_streams(
    domain: str,
    client: AsyncSession,
    subject_id: str,
    detail_path: str | None,
    se: int,
    ep: int,
) -> dict[str, Any]:
    referer = (
        f"{domain}/spa/videoPlayPage/movies/{detail_path or ''}"
        f"?id={subject_id}&type=/movie/detail&detailSe={se or ''}&detailEp={ep or ''}&lang=en"
    )
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "User-Agent": _BROWSER_UA,
        "X-Client-Info": _X_CLIENT_INFO,
        "X-Source": "",
    }
    params: dict[str, Any] = {"subjectId": subject_id, "se": se, "ep": ep}
    if detail_path:
        params["detailPath"] = detail_path

    r = await client.get(
        f"{domain}{_PLAY_PATH}",
        headers=headers,
        params=params,
        cookies=_SESSION_COOKIES,
        timeout=30,
    )
    r.raise_for_status()
    data = (r.json() or {}).get("data") or {}
    streams = data.get("streams") or []
    codecs = sorted({(s.get("codecName") or "?") for s in streams})
    resolutions = sorted({(s.get("resolutions") or "?") for s in streams})
    logger.info(
        "[play] subject_id=%s status=%d streams=%d codecs=%s resolutions=%s",
        subject_id, r.status_code, len(streams), codecs, resolutions,
    )
    return data


async def _fetch_captions(
    domain: str,
    client: AsyncSession,
    subject_id: str,
    detail_path: str | None,
    se: int,
    ep: int,
) -> list[dict[str, str]]:
    headers = {
        "Accept": "application/json",
        "Referer": f"{domain}/movies/{detail_path or ''}",
        "User-Agent": _BROWSER_UA,
        "X-Client-Info": _X_CLIENT_INFO,
    }
    params = {"subjectId": subject_id, "se": se, "ep": ep}
    try:
        r = await client.get(
            f"{domain}{_DOWNLOAD_PATH}",
            headers=headers,
            params=params,
            cookies=_SESSION_COOKIES,
            timeout=20,
        )
        r.raise_for_status()
        captions = ((r.json() or {}).get("data") or {}).get("captions") or []
    except Exception:
        return []
    return [
        {"lang": c.get("lanName") or c.get("lan") or "", "url": c.get("url") or ""}
        for c in captions
        if c.get("url")
    ]


async def _fetch_download_files(
    client: MovieBoxHttpClient,
    subject_id: str,
    season: int,
    episode: int,
    *,
    max_pages: int = 5,
) -> list[VideoFileMetadata]:
    """Page MovieBox's mobile resource endpoint and return files matching
    (season, episode). Movies map to season=0/episode=0 in this API, in which
    case any returned files belong to the movie itself."""
    found: list[VideoFileMetadata] = []
    # Dedup on logical identity, NOT the signed URL — MovieBox re-signs on
    # every call so the URL differs across the two passes for the same file.
    seen: set[tuple[int | None, int | None, int | None, str | None]] = set()
    is_series = season != 0 or episode != 0

    # Two passes pick up both the high-quality archive (default resolution)
    # and any low-quality-only episodes the BEST pass would otherwise drop.
    for res in (None, ResolutionType.UNSPECIFIED):
        downloads = (
            DownloadableVideoFilesDetail(client_session=client)
            if res is None
            else DownloadableVideoFilesDetail(client_session=client, resolution=res)
        )
        page = 1
        while page <= max_pages:
            downloads.page = page
            try:
                chunk = await downloads.get_content_model(subject_id=subject_id)
            except Exception:
                break
            for v in chunk.list:
                if is_series and (v.season != season or v.episode != episode):
                    continue
                key = (
                    v.season,
                    v.episode,
                    v.resolution,
                    getattr(v, "codec_name", None),
                )
                if key in seen:
                    continue
                seen.add(key)
                found.append(v)
            if not chunk.pager.has_more:
                break
            next_page = chunk.pager.next_page or (page + 1)
            if next_page <= page:
                break
            page = next_page
    return found


def _is_hevc(codec: str | None, url: str | None = None) -> bool:
    c = (codec or "").lower()
    if "hevc" in c or "265" in c:
        return True
    if url:
        u = url.lower()
        # Check for common HEVC markers in URLs
        if "/h265/" in u or "/hevc/" in u:
            return True
    return False


def _select_best_stream(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not streams:
        return None

    def res(s: dict[str, Any]) -> int:
        try:
            return int(str(s.get("resolution") or s.get("resolutions") or 0).rstrip("p"))
        except (TypeError, ValueError):
            return 0

    return max(streams, key=res)


def _merge_for_player(
    play: list[dict[str, Any]], download: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Combine H5 play and mobile download variants, deduping by resolution.
    Prefer H.264 (iOS Safari can't play hev1); fall back to HEVC only when no
    H.264 exists at any resolution, so the player has something to attempt
    instead of showing 'Source Unavailable'. download_qualities stays
    unfiltered so the Downloads UI keeps everything."""
    h264: dict[str, dict[str, Any]] = {}
    hevc: dict[str, dict[str, Any]] = {}
    for q in play + download:
        r = q.get("resolution")
        if not r:
            continue
        if _is_hevc(q.get("codec") or q.get("codecName"), q.get("url")):
            if r not in hevc:
                hevc[r] = q
        elif r not in h264:
            h264[r] = q

    chosen = h264 if h264 else hevc
    return sorted(
        chosen.values(),
        key=lambda q: int(str(q["resolution"]).rstrip("p")),
        reverse=True,
    )


async def _resolve(
    title: str,
    year: int | None,
    subject_type: SubjectType,
    season: int | None = None,
    episode: int | None = None,
) -> dict[str, Any] | None:
    se, ep = season or 0, episode or 0
    async with MovieBoxHttpClient() as client:
        candidates = await _search_candidates(client, title, subject_type)
        match = best_match(title, year, candidates)
        if match is None:
            return None
        target_subject_id, detail_path = await _resolve_target(
            client, match.subject_id, match.detail_path
        )

        # Kick off mobile download lookup and domain discovery in parallel.
        download_task = _fetch_download_files(client, target_subject_id, se, ep)

        async with AsyncSession(impersonate=_IMPERSONATE) as web:
            domain_task = _resolve_play_domain(web)

            # Wait for both initial tasks.
            download_files, domain = await asyncio.gather(download_task, domain_task)

            # Now fetch play streams and captions in parallel using the domain.
            streams_task = _fetch_play_streams(
                domain, web, target_subject_id, detail_path, se, ep
            )
            captions_task = _fetch_captions(
                domain, web, target_subject_id, detail_path, se, ep
            )

            try:
                play_data = await streams_task
                streams = play_data.get("streams") or []
            except Exception as e:
                logger.warning(
                    "[play] subject_id=%s fetch failed: %s",
                    target_subject_id, e,
                )
                streams = []

            captions = await captions_task

    qualities: list[dict[str, Any]] = []
    for s in streams:
        url = s.get("url")
        resolution = s.get("resolutions")
        if not url or not resolution:
            continue
        qualities.append(
            {
                "resolution": f"{resolution}p",
                "size_bytes": s.get("size") or 0,
                "url": url,
                "codec": s.get("codecName") or "",
                "format": s.get("format") or "",
            }
        )
    qualities.sort(key=lambda q: int(str(q["resolution"]).rstrip("p")), reverse=True)

    download_qualities: list[dict[str, Any]] = []
    for v in download_files:
        url = str(v.resource_link) if v.resource_link else None
        if not url or not v.resolution:
            continue
        download_qualities.append(
            {
                "resolution": f"{v.resolution}p",
                "size_bytes": int(v.size or 0),
                "url": url,
                "codec": getattr(v, "codec_name", "") or "",
                "format": "",
            }
        )
    download_qualities.sort(
        key=lambda q: int(str(q["resolution"]).rstrip("p")), reverse=True
    )

    logger.info(
        "[resolve] subject_id=%s play_qualities=%d download_qualities=%d "
        "play_codecs=%s download_codecs=%s",
        target_subject_id,
        len(qualities),
        len(download_qualities),
        sorted({q.get("codec") or "?" for q in qualities}),
        sorted({q.get("codec") or "?" for q in download_qualities}),
    )

    # Coming Soon: nothing to play AND nothing to download.
    if not qualities and not download_qualities:
        return None

    # Merge play + download variants for the streaming pool, dropping HEVC.
    # download_qualities stays untouched so the Downloads UI keeps HEVC files.
    qualities = _merge_for_player(qualities, download_qualities)
    logger.info(
        "[resolve] subject_id=%s post_merge_qualities=%d post_merge_codecs=%s",
        target_subject_id,
        len(qualities),
        sorted({q.get("codec") or "?" for q in qualities}),
    )

    chosen = _select_best_stream(qualities)
    final_stream_url = chosen["url"] if chosen else None
    final_codec = (chosen.get("codec") if chosen else "") or ""
    final_format = (chosen.get("format") if chosen else "") or ""

    return {
        "stream_url": final_stream_url,
        "stream_codec": final_codec,
        "stream_format": final_format,
        # CDN does Referer-allowlisting against MovieBox's current play domain.
        # The browser can't spoof Referer, so the proxy needs this to fetch bytes.
        "play_referer": domain.rstrip("/") + "/",
        "qualities": qualities,
        "download_qualities": download_qualities,
        "captions": captions,
        "source": "moviebox",
    }


@router.get("/stream/movie")
async def stream_movie(
    title: str = Query(...),
    year: int | None = Query(default=None),
    tmdb_id: int | None = Query(default=None),
    anilist_id: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id or anilist_id, title, year, None, None)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    resolved = await _resolve(title, year, SubjectType.MOVIES)
    if resolved is None:
        raise HTTPException(status_code=404, detail={"error": "unavailable"})

    _cache.set(key, resolved)
    return resolved


@router.get("/stream/series")
async def stream_series(
    title: str = Query(...),
    season: int = Query(...),
    episode: int = Query(...),
    year: int | None = Query(default=None),
    tmdb_id: int | None = Query(default=None),
    anilist_id: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id or anilist_id, title, year, season, episode)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    resolved = await _resolve(
        title, year, SubjectType.TV_SERIES, season=season, episode=episode
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail={"error": "unavailable"})

    _cache.set(key, resolved)
    return resolved
