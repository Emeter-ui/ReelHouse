"""Diagnostic endpoint: dump raw MovieBox metadata for a series.

Use to investigate why specific episodes don't resolve — exposes what
MovieBox actually returns (season/episode tagging, resolutions, candidate
matches) before we filter it.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from curl_cffi.requests import AsyncSession
from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.constants import ResolutionType
from moviebox_api.v3.core import DownloadableVideoFilesDetail, ItemDetails, Search
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.models.downloadables import VideoFileMetadata
from moviebox_api.v3.urls import PLAY_INFO_PATH, RESOURCE_PATH

from ..matching import Candidate, best_match


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

router = APIRouter()


@router.get("/debug/moviebox-probe")
async def moviebox_probe(
    title: str = Query("Inception", description="Title to search for"),
    year: int | None = Query(default=2010),
) -> dict[str, Any]:
    """Hit every MovieBox surface from the deployed backend and report which
    succeed/fail. Used to confirm whether MovieBox is IP-blocking the host.

    Returns timing + status + error per call so we can tell exactly which
    endpoints are blocked vs working.
    """
    report: dict[str, Any] = {"host": "render", "checks": {}}

    async def timed(label: str, coro):
        t0 = time.monotonic()
        try:
            data = await coro
            report["checks"][label] = {
                "ok": True,
                "ms": int((time.monotonic() - t0) * 1000),
                "summary": data,
            }
            return data
        except httpx.HTTPStatusError as exc:
            report["checks"][label] = {
                "ok": False,
                "ms": int((time.monotonic() - t0) * 1000),
                "kind": "http_status",
                "status": exc.response.status_code,
                "body_preview": exc.response.text[:300],
            }
        except Exception as exc:
            report["checks"][label] = {
                "ok": False,
                "ms": int((time.monotonic() - t0) * 1000),
                "kind": type(exc).__name__,
                "error": str(exc)[:500],
            }
        return None

    # 1) Plain GET to H5 domain discovery — no signing, just a vanilla request.
    async def check_discovery():
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://h5-api.aoneroom.com/wefeed-h5api-bff/media-player/get-domain",
                headers={"User-Agent": "Mozilla/5.0", "X-Client-Type": "h5"},
            )
            r.raise_for_status()
            j = r.json() or {}
            return {"play_domain": j.get("data"), "code": j.get("code")}

    discovery = await timed("h5_domain_discovery", check_discovery())
    play_domain = (discovery or {}).get("play_domain") or "https://h5.aoneroom.com"
    play_domain = play_domain.rstrip("/")

    # 2) Mobile-bff search (signed POST) — this is the most likely IP-blocked call.
    subject_id: str | None = None
    detail_path: str | None = None
    async def check_search():
        nonlocal subject_id, detail_path
        async with MovieBoxHttpClient() as client:
            search = Search(
                client_session=client, query=title, subject_type=SubjectType.MOVIES
            )
            result = await search.get_content_model()
            cands = []
            for item in result.items:
                if not item.has_resource:
                    continue
                yr = item.release_date.year if item.release_date else None
                cands.append(Candidate(
                    subject_id=item.subject_id,
                    title=item.title,
                    year=yr,
                ))
            match = best_match(title, year, cands)
            if match:
                subject_id = match.subject_id
            return {
                "items": len(result.items),
                "candidates": len(cands),
                "matched_subject_id": subject_id,
                "matched_title": match.title if match else None,
            }

    await timed("mobile_search", check_search())

    # 3) Mobile-bff item-details (signed GET) — same auth surface as search.
    if subject_id:
        async def check_details():
            async with MovieBoxHttpClient() as client:
                d = await ItemDetails(client_session=client).get_content_model(subject_id)
                return {
                    "title": d.title,
                    "subject_id": d.subject_id,
                    "dubs": len(d.dubs),
                }
        await timed("mobile_item_details", check_details())

        # 4) Mobile-bff resource (signed) — what /stream uses for download_qualities.
        async def check_resource():
            async with MovieBoxHttpClient() as client:
                downloads = DownloadableVideoFilesDetail(
                    client_session=client, resolution=ResolutionType.UNSPECIFIED
                )
                downloads.page = 1
                chunk = await downloads.get_content_model(subject_id=subject_id)
                return {"file_count": len(chunk.list)}
        await timed("mobile_resource", check_resource())

    # 5) H5 /subject/play (no signing, browser-style) — same call we proved
    #    is reachable from the browser. Tests whether the BACKEND host is
    #    blocked even on the H5 surface.
    if subject_id:
        async def check_play():
            async with AsyncSession(impersonate="chrome124") as web:
                r = await web.get(
                    f"{play_domain}/wefeed-h5api-bff/subject/play",
                    params={"subjectId": subject_id, "se": 0, "ep": 0},
                    headers={
                        "Accept": "application/json",
                        "Referer": f"{play_domain}/",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "X-Client-Info": '{"timezone":"Africa/Nairobi"}',
                    },
                    cookies={"uuid": "d8c3539e-2e46-4000-af20-7046a856e30a"},
                    timeout=15,
                )
                r.raise_for_status()
                data = (r.json() or {}).get("data") or {}
                streams = data.get("streams") or []
                return {
                    "stream_count": len(streams),
                    "resolutions": sorted({str(s.get("resolutions")) for s in streams}),
                    "codecs": sorted({s.get("codecName") for s in streams}),
                    "first_url_host": (
                        streams[0]["url"].split("/")[2] if streams else None
                    ),
                }
        await timed("h5_play", check_play())

    # Roll up which surfaces work — makes the "what's blocked" call obvious.
    report["summary"] = {
        name: ("ok" if v.get("ok") else f"FAIL ({v.get('kind') or v.get('status')})")
        for name, v in report["checks"].items()
    }
    return report


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
