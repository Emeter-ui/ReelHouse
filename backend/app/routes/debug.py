"""Diagnostic endpoint: dump raw MovieBox metadata for a series.

Use to investigate why specific episodes don't resolve — exposes what
MovieBox actually returns (season/episode tagging, resolutions, candidate
matches) before we filter it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.core import Search
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.urls import PLAY_INFO_PATH, RESOURCE_PATH

from ..matching import Candidate, best_match
from .stream import fetch_all_video_files

router = APIRouter()


@router.get("/debug/full-resource")
async def full_resource(
    subject_id: str = Query(...),
) -> dict[str, Any]:
    """Walk all pages with resolution=0 and dump every (season, episode, resolution)."""
    async with MovieBoxHttpClient() as client:
        all_items: list[dict[str, Any]] = []
        page = 1
        while page <= 50:
            params = {
                "subjectId": subject_id, "resolution": 0,
                "page": page, "perPage": 20,
            }
            try:
                raw = await client.get_from_api(RESOURCE_PATH, params=params)
            except Exception as exc:
                return {"error": str(exc), "page_failed": page, "collected": all_items}
            items = raw.get("list") or []
            for f in items:
                all_items.append({
                    "se": f.get("se"),
                    "ep": f.get("ep"),
                    "resolution": f.get("resolution"),
                    "size": f.get("size"),
                })
            pager = raw.get("pager") or {}
            if not pager.get("hasMore"):
                break
            page += 1
        # group by (se, ep)
        by_episode: dict[str, list[int]] = {}
        for it in all_items:
            key = f"S{it['se']}E{it['ep']}"
            by_episode.setdefault(key, []).append(it["resolution"])
        return {
            "total_items": len(all_items),
            "unique_episodes": len(by_episode),
            "by_episode": dict(sorted(by_episode.items())),
        }


@router.get("/debug/play-info-sweep")
async def play_info_sweep(
    subject_id: str = Query(...),
    season: int = Query(...),
    episodes: str = Query("1,2,3,4,5,6,7,8", description="Comma-separated episode numbers"),
) -> dict[str, Any]:
    """Hit play-info for each episode in the list and report what's available."""
    async with MovieBoxHttpClient() as client:
        results: list[dict[str, Any]] = []
        for ep_str in episodes.split(","):
            ep = int(ep_str.strip())
            params = {"subjectId": subject_id, "se": season, "ep": ep}
            try:
                raw = await client.get_from_api(PLAY_INFO_PATH, params=params)
                streams = raw.get("streams") or []
                results.append({
                    "episode": ep,
                    "title": raw.get("title"),
                    "stream_count": len(streams),
                    "formats": list({s.get("format") for s in streams}),
                    "resolutions": [s.get("resolutions") for s in streams],
                    "duration": streams[0].get("duration") if streams else None,
                })
            except Exception as exc:
                results.append({"episode": ep, "error": str(exc)})
        return {"subject_id": subject_id, "season": season, "results": results}



@router.get("/debug/probe-episode")
async def probe_episode(
    subject_id: str = Query(..., description="MovieBox subject_id"),
    season: int = Query(...),
    episode: int = Query(...),
) -> dict[str, Any]:
    """Probe the raw resource endpoint with several param combos to see which
    (if any) returns files for episodes missing from the bulk paginated listing."""
    async with MovieBoxHttpClient() as client:
        attempts: list[dict[str, Any]] = []

        async def try_params(label: str, params: dict[str, Any]) -> None:
            try:
                raw = await client.get_from_api(RESOURCE_PATH, params=params)
            except Exception as exc:
                attempts.append({"label": label, "params": params, "error": str(exc)})
                return
            files = raw.get("list") or []
            attempts.append({
                "label": label,
                "params": params,
                "list_count": len(files),
                "pager": raw.get("pager"),
                "matching_episode_count": sum(
                    1 for f in files if f.get("se") == season and f.get("ep") == episode
                ),
                "sample_files": [
                    {
                        "se": f.get("se"),
                        "ep": f.get("ep"),
                        "resolution": f.get("resolution"),
                        "size": f.get("size"),
                    }
                    for f in files[:5]
                ],
            })

        await try_params("se+ep", {
            "subjectId": subject_id, "se": season, "ep": episode,
            "resolution": 0, "page": 1, "perPage": 20,
        })
        await try_params("se+ep+all=1", {
            "subjectId": subject_id, "se": season, "ep": episode,
            "all": 1, "resolution": 0, "page": 1, "perPage": 20,
        })
        await try_params("se only", {
            "subjectId": subject_id, "se": season,
            "resolution": 0, "page": 1, "perPage": 20,
        })
        await try_params("epFrom/epTo", {
            "subjectId": subject_id,
            "epFrom": episode, "epTo": episode,
            "resolution": 0, "page": 1, "perPage": 20,
        })
        await try_params("all=1 only", {
            "subjectId": subject_id, "all": 1,
            "resolution": 0, "page": 1, "perPage": 20,
        })

        # Probe the streaming endpoint (different path; what the website's player calls)
        play_info_attempts: list[dict[str, Any]] = []
        for label, params in [
            ("play-info se+ep", {"subjectId": subject_id, "se": season, "ep": episode}),
            ("play-info no-args", {"subjectId": subject_id}),
        ]:
            try:
                raw = await client.get_from_api(PLAY_INFO_PATH, params=params)
                play_info_attempts.append({"label": label, "params": params, "raw": raw})
            except Exception as exc:
                play_info_attempts.append({"label": label, "params": params, "error": str(exc)})

        return {
            "subject_id": subject_id,
            "season": season,
            "episode": episode,
            "resource_attempts": attempts,
            "play_info_attempts": play_info_attempts,
        }



@router.get("/debug/series")
async def debug_series(
    title: str = Query(..., description="Series title (what we search MovieBox with)"),
    year: int | None = Query(default=None),
    season: int | None = Query(default=None, description="Optional: filter dump to this season"),
) -> dict[str, Any]:
    async with MovieBoxHttpClient() as client:
        search = Search(client_session=client, query=title, subject_type=SubjectType.TV_SERIES)
        try:
            search_result = await search.get_content_model()
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": "search_failed", "message": str(exc)})

        candidates: list[Candidate] = []
        candidate_dump: list[dict[str, Any]] = []
        for item in search_result.items:
            yr = item.release_date.year if item.release_date else None
            candidate_dump.append({
                "subject_id": item.subject_id,
                "title": item.title,
                "year": yr,
                "has_resource": item.has_resource,
            })
            if item.has_resource:
                candidates.append(Candidate(subject_id=item.subject_id, title=item.title, year=yr))

        match = best_match(title, year, candidates)
        if match is None:
            return {
                "matched": None,
                "candidates": candidate_dump,
                "files": [],
                "note": "no candidate passed matching thresholds",
            }

        page_trace: list[dict[str, Any]] = []
        try:
            all_files = await fetch_all_video_files(client, match.subject_id, trace=page_trace)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": "files_fetch_failed", "message": str(exc)})
        if season is not None:
            filtered = [v for v in all_files if v.season == season]
        else:
            filtered = all_files

        files_dump = [
            {
                "season": v.season,
                "episode": v.episode,
                "resolution": v.resolution,
                "codec": getattr(v, "codec_name", None),
                "size_bytes": v.size,
                "url": str(v.resource_link) if v.resource_link else None,
            }
            for v in filtered
        ]
        files_dump.sort(key=lambda f: (f["season"] or 0, f["episode"] or 0, -(f["resolution"] or 0)))

        codec_breakdown: dict[str, int] = {}
        for v in filtered:
            c = getattr(v, "codec_name", None) or "unknown"
            codec_breakdown[c] = codec_breakdown.get(c, 0) + 1
        # marker: force-reload-touch

        seasons_present = sorted({v.season for v in all_files if v.season is not None})
        episodes_in_filter = sorted({v.episode for v in filtered if v.episode is not None})

        return {
            "matched": {
                "subject_id": match.subject_id,
                "title": match.title,
                "year": match.year,
            },
            "candidates": candidate_dump,
            "summary": {
                "total_files": len(all_files),
                "filtered_files": len(files_dump),
                "seasons_present": seasons_present,
                "episodes_in_filter": episodes_in_filter,
                "files_with_no_resolution": sum(1 for v in filtered if not v.resolution),
                "codec_breakdown": codec_breakdown,
            },
            "pagination_trace": page_trace,
            "files": files_dump,
        }
