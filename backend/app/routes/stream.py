"""Resolve a TMDB title to a moviebox stream URL + qualities + captions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.constants import ResolutionType
from moviebox_api.v3.core import (
    DownloadableCaptionFileDetails,
    DownloadableVideoFilesDetail,
    ItemDetails,
    Search,
)
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.models.downloadables import VideoFileMetadata

from ..cache import TTLCache
from ..matching import Candidate, best_match

router = APIRouter()

_cache = TTLCache(maxsize=512, ttl_seconds=30 * 60)


def _cache_key(tmdb_id: int, season: int | None, episode: int | None) -> str:
    return f"{tmdb_id}:{season or ''}:{episode or ''}"


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
        out.append(Candidate(subject_id=item.subject_id, title=item.title, year=year))
    return out


def _pick_best_video(
    videos: list[VideoFileMetadata],
    season: int | None = None,
    episode: int | None = None,
) -> VideoFileMetadata | None:
    if season is not None and episode is not None:
        videos = [v for v in videos if v.season == season and v.episode == episode]
    if not videos:
        return None
    
    # Prefer non-HEVC (e.g. h264) for web playback.
    def is_hevc(v: VideoFileMetadata) -> bool:
        codec = (v.codec_name or "").lower()
        url = str(v.resource_link).lower()
        return "hevc" in codec or "265" in codec or "/h265/" in url or "/hevc/" in url
        
    non_hevc = [v for v in videos if not is_hevc(v)]
    if non_hevc:
        return max(non_hevc, key=lambda v: v.resolution)
        
    return max(videos, key=lambda v: v.resolution)


# MovieBox caps per_page at 20, so a long-running series spans many pages.
# Without paging, we silently miss every episode after the first 20.
async def fetch_all_video_files(
    client: MovieBoxHttpClient,
    subject_id: str,
    *,
    max_pages: int = 50,
    trace: list[dict[str, Any]] | None = None,
) -> list[VideoFileMetadata]:
    # The MovieBox /resource endpoint returns at most one quality tier per call.
    # - resolution=BEST  → only episodes that have a 1080p archive (drops episodes
    #                      that only exist at lower qualities, making them invisible).
    # - resolution=UNSPECIFIED → returns each episode at its lowest-published
    #                            quality (typically 360p), but for *every* episode.
    # Hitting both and merging is the only way to get complete episode coverage
    # AND high-resolution files where they exist.
    collected: list[VideoFileMetadata] = []
    # Include codec_name in the dedup key so h264 and h265 variants of the same
    # (season, episode, resolution) both survive if MovieBox happens to ship both.
    seen_keys: set[tuple[int | None, int | None, int | None, str | None]] = set()

    for pass_label, res in (("best", None), ("unspecified", ResolutionType.UNSPECIFIED)):
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
            except Exception as exc:
                if trace is not None:
                    trace.append({"pass": pass_label, "page": page, "error": str(exc)})
                break
            if trace is not None:
                trace.append({
                    "pass": pass_label,
                    "page": page,
                    "items": len(chunk.list),
                    "has_more": chunk.pager.has_more,
                    "next_page": chunk.pager.next_page,
                    "total_count": chunk.pager.total_count,
                    "per_page": chunk.pager.per_page,
                })
            for v in chunk.list:
                key = (v.season, v.episode, v.resolution, getattr(v, "codec_name", None))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                collected.append(v)
            if not chunk.pager.has_more:
                break
            next_page = chunk.pager.next_page or (page + 1)
            if next_page <= page:
                break
            page = next_page
    return collected


async def _original_dub_subject_id(
    client: MovieBoxHttpClient, subject_id: str
) -> str:
    # MovieBox indexes localized dubs (Hindi, Tamil, etc.) under separate
    # subject_ids and often ranks them ahead of the English original in search.
    # Redirect to the Original dub when the matched subject is a localized one.
    try:
        details = await ItemDetails(client_session=client).get_content_model(subject_id)
    except Exception:
        return subject_id
    for dub in details.dubs:
        if dub.original:
            return dub.subject_id
    return subject_id


async def _resolve(
    title: str,
    year: int | None,
    subject_type: SubjectType,
    season: int | None = None,
    episode: int | None = None,
) -> dict[str, Any] | None:
    async with MovieBoxHttpClient() as client:
        candidates = await _search_candidates(client, title, subject_type)
        match = best_match(title, year, candidates)
        if match is None:
            return None

        target_subject_id = await _original_dub_subject_id(client, match.subject_id)
        all_files = await fetch_all_video_files(client, target_subject_id)
        if not all_files:
            return None

        chosen = _pick_best_video(all_files, season=season, episode=episode)
        if chosen is None:
            return None

        captions: list[dict[str, str]] = []
        try:
            cap_meta = DownloadableCaptionFileDetails(client_session=client)
            cap = await cap_meta.get_content_model(
                subject_id=target_subject_id, resource=chosen
            )
            captions = [
                {"lang": c.lan_name, "url": str(c.url)} for c in cap.captions
            ]
        except Exception:
            pass

        # For series, restrict to the same (season, episode); else use all files.
        relevant = (
            [v for v in all_files if v.season == season and v.episode == episode]
            if season is not None and episode is not None
            else all_files
        )
        qualities = [
            {
                "resolution": f"{v.resolution}p",
                "size_bytes": v.size,
                "url": str(v.resource_link),
                "codec": v.codec_name,
            }
            for v in relevant
            if v.resolution
        ]
        qualities.sort(key=lambda q: int(q["resolution"].rstrip("p")), reverse=True)

        return {
            "stream_url": str(chosen.resource_link),
            "qualities": qualities,
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
