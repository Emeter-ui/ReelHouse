"""Shared factory for the MovieBox v3 client.

When MOVIEBOX_API_PROXY is set, all v3 traffic (search, details, downloads)
routes through that proxy to dodge MovieBox's anti-bot on datacenter egress.
Unset = direct connection (works fine on localhost).

This is separate from MOVIEBOX_PROXY_URL (the Cloudflare Worker that fronts
the H5 play domain) — both proxies cover different traffic and coexist.
"""
from __future__ import annotations

import os

from moviebox_api.v3.http_client import MovieBoxHttpClient

_MOVIEBOX_API_PROXY = os.environ.get("MOVIEBOX_API_PROXY", "").strip()


def make_client() -> MovieBoxHttpClient:
    if _MOVIEBOX_API_PROXY:
        return MovieBoxHttpClient(proxy=_MOVIEBOX_API_PROXY)
    return MovieBoxHttpClient()
