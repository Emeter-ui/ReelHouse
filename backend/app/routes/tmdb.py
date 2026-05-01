"""Catch-all TMDB proxy. Frontend calls /api/tmdb/<path>?<query>; backend
appends the API key, caches successful responses for 1h."""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..cache import TTLCache
from ..config import get_settings

router = APIRouter()

_cache = TTLCache(maxsize=2048, ttl_seconds=3600)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    return _client


def _cache_key(path: str, query_items: list[tuple[str, str]]) -> str:
    return path + "?" + "&".join(f"{k}={v}" for k, v in sorted(query_items))


@router.get("/tmdb/{path:path}")
async def tmdb_proxy(path: str, request: Request) -> Any:
    settings = get_settings()

    # Strip any client-sent api_key so the server's key always wins.
    query_items = [
        (k, v) for k, v in request.query_params.multi_items() if k != "api_key"
    ]
    cache_key = _cache_key(path, query_items)

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    params = dict(query_items)
    params["api_key"] = settings.tmdb_api_key

    url = f"{settings.tmdb_base_url}/{path.lstrip('/')}"

    client = _get_client()
    try:
        resp = await client.get(url, params=params)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"TMDB upstream error: {e}") from e

    if resp.status_code >= 400:
        # Surface TMDB's body but don't cache.
        try:
            detail = resp.json()
        except json.JSONDecodeError:
            detail = {"error": resp.text}
        raise HTTPException(status_code=resp.status_code, detail=detail)

    data = resp.json()
    _cache.set(cache_key, data)
    return data
