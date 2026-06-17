"""Shared factory for the MovieBox v3 client.

Fly's Mumbai (`bom`) egress IP is not blocked by MovieBox on any of the
mobile-bff endpoints (search, item-details, season-info, play-info,
resource) — verified live via `/api/debug/moviebox-probe`. So we call
MovieBox directly from the backend and skip the Cloudflare Worker for
these requests. The Worker is still required for CDN byte tunneling
(see proxy.py) and remains the fallback if we ever return to a
blocked region.

``MOVIEBOX_API_PROXY`` (separate from the Worker URL) lets callers route
the API through an httpx-style proxy — useful for upstream debugging or
if a new region gets flagged.
"""
from __future__ import annotations

import os

from moviebox_api.v3.http_client import MovieBoxHttpClient

_MOVIEBOX_API_PROXY = os.environ.get("MOVIEBOX_API_PROXY", "").strip()


def make_client() -> MovieBoxHttpClient:
    if _MOVIEBOX_API_PROXY:
        return MovieBoxHttpClient(proxy=_MOVIEBOX_API_PROXY)
    return MovieBoxHttpClient()
