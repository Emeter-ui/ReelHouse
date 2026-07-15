"""Donghua (and general anime) via self-hosted Consumet API.

Consumet returns HLS `.m3u8` sources — a different pipeline from MovieBox's
progressive MP4. We keep the same `StreamResolveResponse`-ish shape the
frontend Player already understands (video.js VHS plays HLS from a `.m3u8`
URL without extra config), so the donghua watch page can reuse Player.vue.

Zoro is the primary provider; AnimeKai is the fallback used automatically
when Zoro's search returns nothing or the episode-watch endpoint errors.

Downloads are intentionally NOT implemented in this pass — Consumet has no
MP4 download endpoint, so we'll do an ffmpeg HLS→MP4 transmux later.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..cache import TTLCache
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_settings = get_settings()

# Consumet upstream can be slow (30s+ for a cold Zoro search); keep a
# generous timeout but not unbounded.
_HTTP_TIMEOUT = 30.0

# Search + info are stable enough to cache aggressively. Watch (stream)
# resolves signed CDN URLs — keep TTL short so links don't expire mid-play.
_search_cache = TTLCache(maxsize=512, ttl_seconds=6 * 3600)
_info_cache = TTLCache(maxsize=512, ttl_seconds=3600)
_watch_cache = TTLCache(maxsize=1024, ttl_seconds=3 * 60)

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            base_url=_settings.consumet_base_url,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
    return _http


# Providers ordered by preference. Consumet accepts these as URL segments
# under /anime/{provider}/. AnimeKai works as a drop-in shape-wise.
_PROVIDERS = ("zoro", "animekai")


async def _consumet_get(path: str) -> Any:
    """GET a Consumet path, raising HTTPException with useful context on failure."""
    try:
        resp = await _client().get(path)
    except httpx.HTTPError as e:
        logger.warning("consumet %s failed: %s", path, e)
        raise HTTPException(status_code=502, detail=f"consumet upstream error: {e}") from e
    if resp.status_code >= 500:
        raise HTTPException(status_code=502, detail=f"consumet {resp.status_code} on {path}")
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:200])
    try:
        return resp.json()
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"consumet non-JSON response: {e}") from e


@router.get("/donghua/search")
async def search(
    q: str = Query(..., min_length=1, description="Show title to search for."),
    page: int = Query(1, ge=1, le=20),
) -> dict[str, Any]:
    """Search across preferred providers, returning the first non-empty result set.

    Response shape:
        {
          "provider": "zoro" | "animekai",
          "hasNextPage": bool,
          "results": [{ id, title, image, type, releaseDate?, subOrDub? }, ...],
        }
    """
    key = f"search:{q.lower()}:{page}"
    cached = _search_cache.get(key)
    if cached is not None:
        return cached

    encoded = quote(q, safe="")
    last_error: Exception | None = None
    for provider in _PROVIDERS:
        try:
            data = await _consumet_get(f"/anime/{provider}/{encoded}?page={page}")
        except HTTPException as e:
            last_error = e
            continue
        results = (data or {}).get("results") or []
        if results:
            payload = {
                "provider": provider,
                "hasNextPage": bool((data or {}).get("hasNextPage")),
                "results": results,
            }
            _search_cache.set(key, payload)
            return payload

    if last_error is not None:
        raise last_error
    payload = {"provider": _PROVIDERS[0], "hasNextPage": False, "results": []}
    _search_cache.set(key, payload)
    return payload


@router.get("/donghua/info")
async def info(
    id: str = Query(..., description="Provider-scoped anime id (from /search)."),
    provider: str = Query("zoro", description="One of: zoro, animekai."),
) -> dict[str, Any]:
    """Episode list + metadata for one show.

    Passthrough of Consumet's info response, cached. Shape includes:
        id, title, image, description, releaseDate, status, totalEpisodes,
        episodes: [{ id, number, title?, isFiller? }, ...]
    """
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")
    key = f"info:{provider}:{id}"
    cached = _info_cache.get(key)
    if cached is not None:
        return cached
    data = await _consumet_get(f"/anime/{provider}/info?id={quote(id, safe='')}")
    if data is None:
        raise HTTPException(status_code=404, detail=f"info not found on {provider}: {id}")
    _info_cache.set(key, data)
    return data


@router.get("/donghua/stream")
async def stream(
    ep: str = Query(..., description="Episode id from info.episodes[].id."),
    provider: str = Query("zoro"),
) -> dict[str, Any]:
    """Resolve a playable stream for one episode.

    Consumet-server returns iframe embed URLs (megaplay.buzz + vidnest.fun)
    now — not raw HLS — because the underlying player's .m3u8 is wrapped in
    rotating encryption we don't maintain. `stream_format: "iframe"` flags
    this to the frontend, which renders a full-page <iframe> instead of the
    video.js Player.

    Falls back to the second-priority source if the first upstream errors.
    Real cross-provider retry (Zoro → AnimeKai) is a frontend concern —
    episode ids are provider-scoped.
    """
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    key = f"watch:{provider}:{ep}"
    cached = _watch_cache.get(key)
    if cached is not None:
        return cached

    last_error: Exception | None = None
    encoded_ep = quote(ep, safe="")
    path = f"/anime/{provider}/watch/{encoded_ep}"
    try:
        data = await _consumet_get(path)
    except HTTPException as e:
        last_error = e
        data = None

    if data:
        sources = data.get("sources") or []
        # Prefer HLS if the source has it (older Consumet shape); otherwise
        # the first source URL — that's what iframe embeds return.
        m3u8 = next(
            (s.get("url") for s in sources if s.get("isM3U8") or ".m3u8" in (s.get("url") or "")),
            None,
        )
        primary_source = None
        if m3u8:
            primary_url = m3u8
            primary_format = "hls"
        elif sources:
            primary_source = sources[0]
            primary_url = primary_source.get("url")
            primary_format = "iframe" if primary_source.get("type") == "iframe" else "mp4"
        else:
            primary_url = None
            primary_format = None

        if primary_url:
            headers = data.get("headers") or {}
            payload = {
                "stream_url": primary_url,
                "stream_format": primary_format,
                # HLS from provider defaults to H.264; iframes have no fixed codec.
                "stream_codec": "h264" if primary_format == "hls" else "",
                "play_referer": headers.get("Referer") or headers.get("referer"),
                "qualities": [
                    {
                        "resolution": s.get("quality") or "auto",
                        "size_bytes": 0,
                        "url": s.get("url"),
                        "codec": "h264" if s.get("isM3U8") else "",
                        # Frontend Player switches on this: 'iframe' triggers
                        # the embed renderer, empty falls back to <video>.
                        "format": "hls" if s.get("isM3U8") else (
                            "iframe" if s.get("type") == "iframe" else ""
                        ),
                        "server": s.get("server") or "",
                    }
                    for s in sources
                    if s.get("url")
                ],
                "download_qualities": [],
                "captions": [
                    {"lang": sub.get("lang") or "und", "url": sub.get("url")}
                    for sub in (data.get("subtitles") or [])
                    if sub.get("url")
                ],
                "source": f"consumet:{provider}",
            }
            _watch_cache.set(key, payload)
            return payload

    if last_error is not None:
        raise last_error
    raise HTTPException(status_code=404, detail=f"no playable source for {ep} on {provider}")
