"""Resolve a TMDB title to a moviebox stream URL + qualities + captions.

Hits MovieBox's web `/subject/play` endpoint (the same one the official h5
player and third-party sites like mymuvies use). Avoids `/subject-api/resource`
because that's the mobile download endpoint — its URLs are HEVC-dominant and
not designed for browser `<video>`.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.constants import ResolutionType
from moviebox_api.v3.core import DownloadableVideoFilesDetail, ItemDetails, Search
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.models.downloadables import VideoFileMetadata

from ..cache import TTLCache
from ..matching import Candidate, best_match

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


def _cache_key(tmdb_id: int, season: int | None, episode: int | None) -> str:
    return f"{tmdb_id}:{season or ''}:{episode or ''}"


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


async def _resolve_play_domain(client: httpx.AsyncClient) -> str:
    try:
        r = await client.get(
            _PLAY_DOMAIN_DISCOVERY,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "application/json",
                "X-Client-Info": _X_CLIENT_INFO,
                "X-Client-Type": "h5",
            },
            timeout=5,
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
    client: httpx.AsyncClient,
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
        timeout=15,
    )
    r.raise_for_status()
    return (r.json() or {}).get("data") or {}


async def _fetch_captions(
    domain: str,
    client: httpx.AsyncClient,
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
            timeout=10,
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
    max_pages: int = 25,
) -> list[VideoFileMetadata]:
    """Page MovieBox's mobile resource endpoint and return files matching
    (season, episode). Movies map to season=0/episode=0 in this API, in which
    case any returned files belong to the movie itself."""
    found: list[VideoFileMetadata] = []
    seen: set[tuple[int | None, int | None, str | None, str]] = set()
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
                    v.resolution,
                    getattr(v, "codec_name", None),
                    str(v.resource_link),
                    "v",
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


def _select_best_stream(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not streams:
        return None

    def is_hevc(s: dict[str, Any]) -> bool:
        codec = (s.get("codecName") or "").lower()
        return "hevc" in codec or "265" in codec

    def res(s: dict[str, Any]) -> int:
        try:
            return int(s.get("resolutions") or 0)
        except (TypeError, ValueError):
            return 0

    non_hevc = [s for s in streams if not is_hevc(s)]
    pool = non_hevc or streams
    return max(pool, key=res)


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
        # Mobile-resource lookup uses the same MovieBoxHttpClient session.
        # Empty/error means downloads simply aren't available.
        try:
            download_files = await _fetch_download_files(
                client, target_subject_id, se, ep
            )
        except Exception:
            download_files = []

    async with httpx.AsyncClient() as web:
        domain = await _resolve_play_domain(web)
        try:
            play_data = await _fetch_play_streams(
                domain, web, target_subject_id, detail_path, se, ep
            )
            streams = play_data.get("streams") or []
        except httpx.HTTPError:
            streams = []

        captions = await _fetch_captions(
            domain, web, target_subject_id, detail_path, se, ep
        )

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

    # Coming Soon: nothing to play AND nothing to download.
    if not qualities and not download_qualities:
        return None

    chosen = _select_best_stream(streams) if streams else None

    return {
        "stream_url": chosen["url"] if chosen else None,
        "stream_codec": (chosen.get("codecName") if chosen else "") or "",
        "stream_format": (chosen.get("format") if chosen else "") or "",
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
    tmdb_id: int = Query(...),
    title: str = Query(...),
    year: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id, None, None)
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
    tmdb_id: int = Query(...),
    title: str = Query(...),
    season: int = Query(...),
    episode: int = Query(...),
    year: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id, season, episode)
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
