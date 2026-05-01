"""Resolve a TMDB title to a moviebox stream URL + qualities + captions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.core import (
    DownloadableCaptionFileDetails,
    DownloadableVideoFilesDetail,
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
    return max(videos, key=lambda v: v.resolution)


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

        downloads = DownloadableVideoFilesDetail(client_session=client)
        try:
            files = await downloads.get_content_model(subject_id=match.subject_id)
        except Exception:
            return None

        chosen = _pick_best_video(files.list, season=season, episode=episode)
        if chosen is None:
            return None

        captions: list[dict[str, str]] = []
        try:
            cap_meta = DownloadableCaptionFileDetails(client_session=client)
            cap = await cap_meta.get_content_model(
                subject_id=match.subject_id, resource=chosen
            )
            captions = [
                {"lang": c.lan_name, "url": str(c.url)} for c in cap.captions
            ]
        except Exception:
            pass

        # For series, restrict to the same (season, episode); else use all files.
        relevant = (
            [v for v in files.list if v.season == season and v.episode == episode]
            if season is not None and episode is not None
            else files.list
        )
        qualities = [
            {
                "resolution": f"{v.resolution}p",
                "size_bytes": v.size,
                "url": str(v.resource_link),
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
