"""Shared factory for the MovieBox v3 client.

Fly's Mumbai (`bom`) egress IP is not blocked by MovieBox on any of the
mobile-bff endpoints (search, item-details, season-info, play-info,
resource). So we call MovieBox directly from the backend and skip the
Cloudflare Worker for these requests. The Worker is still required for
CDN byte tunneling (see proxy.py).

Auth: MovieBox's mobile-bff requires a Bearer JWT now. We self-bootstrap
by issuing one signed-but-unauthenticated GET to
``/wefeed-mobile-bff/subject-api/bottom-tab`` — the server responds with
``x-user`` containing a fresh JWT. We cache it process-wide and inject it
into every client until the server hands us a newer one (each response
carries a refreshed token in ``x-user``).

``MOVIEBOX_AUTH_TOKEN`` env var still works as a manual override (used as
the initial token, skipping the bootstrap). ``MOVIEBOX_API_PROXY`` routes
the API through an httpx-style proxy for debugging.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

from moviebox_api.v3.crypto import build_signed_headers
from moviebox_api.v3.constants import CLIENT_INFO, USER_AGENT
from moviebox_api.v3.http_client import MovieBoxHttpClient

logger = logging.getLogger(__name__)

_MOVIEBOX_API_PROXY = os.environ.get("MOVIEBOX_API_PROXY", "").strip()

# Endpoint that hands out an anon JWT without prior auth. The server returns
# the token in the `x-user` response header. Confirmed live 2026-06-26.
_BOOTSTRAP_PATH = "/wefeed-mobile-bff/subject-api/bottom-tab"
_BOOTSTRAP_HOST = "https://api6.aoneroom.com"

# Process-wide token cache + lock to serialize the first bootstrap. The lock
# is bound to the running event loop on first acquisition; we create it
# lazily so it ends up on whichever loop is calling.
_token: str | None = None
_token_lock: asyncio.Lock | None = None


def _initial_token() -> str | None:
    """Pull a manual override from env (skips bootstrap when set)."""
    return os.environ.get("MOVIEBOX_AUTH_TOKEN", "").strip() or None


async def _bootstrap_token() -> str | None:
    """Hit the anon bootstrap endpoint and parse the ``x-user`` JWT.

    Returns None on any upstream failure; callers should fall back to
    whatever cached token exists (or no token, in which case the request
    will get 441 and we'll retry-bootstrap on the next call).
    """
    url = _BOOTSTRAP_HOST + _BOOTSTRAP_PATH
    headers = build_signed_headers(
        method="GET",
        url=url,
        accept="application/json",
        content_type="application/json",
        body=None,
        include_play_mode=False,
        auth_token=None,
        client_info=CLIENT_INFO,
        user_agent=USER_AGENT,
    )
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=headers)
    except Exception as exc:
        logger.warning("[moviebox-bootstrap] request failed: %s", exc)
        return None
    if r.status_code != 200:
        logger.warning(
            "[moviebox-bootstrap] non-200: status=%d body=%r",
            r.status_code, r.text[:200],
        )
        return None
    x_user = r.headers.get("x-user", "")
    if not x_user:
        logger.warning("[moviebox-bootstrap] response missing x-user header")
        return None
    try:
        token = (json.loads(x_user) or {}).get("token") or None
    except Exception as exc:
        logger.warning("[moviebox-bootstrap] x-user not JSON: %s — %r", exc, x_user[:120])
        return None
    if token:
        logger.info("[moviebox-bootstrap] obtained token (len=%d)", len(token))
    return token


async def _ensure_token() -> str | None:
    """Return a cached JWT, bootstrapping if needed. Coalesces concurrent
    callers via a lazy asyncio.Lock so we don't hammer the bootstrap endpoint
    when multiple requests race for the first token."""
    global _token, _token_lock
    if _token:
        return _token
    if _token_lock is None:
        _token_lock = asyncio.Lock()
    async with _token_lock:
        if _token:
            return _token
        _token = _initial_token() or await _bootstrap_token()
        return _token


def _invalidate_token() -> None:
    """Drop the cached token. Called on 401/441 so the next request
    re-bootstraps. Other request paths can keep using their in-flight client."""
    global _token
    if _token is not None:
        logger.info("[moviebox-bootstrap] invalidating cached token")
    _token = None


class _BootstrappingClient(MovieBoxHttpClient):
    """MovieBoxHttpClient that seeds itself with the cached process-wide JWT
    on enter, retries once with a fresh token if the server rejects auth,
    and writes refreshed tokens back to the cache as responses rotate them
    via x-user headers."""

    async def __aenter__(self) -> "_BootstrappingClient":
        await super().__aenter__()
        self._runtime_token = await _ensure_token()
        return self

    def _absorb_x_user(self, headers: httpx.Headers) -> None:
        super()._absorb_x_user(headers)
        # Mirror the freshly-rotated token into the module-level cache so
        # the next client instance starts from the latest token rather than
        # the one we first bootstrapped with.
        global _token
        if self._runtime_token and self._runtime_token != _token:
            _token = self._runtime_token

    async def _request(self, method: str, path_and_query: str, **kwargs: Any):
        no_retry = kwargs.pop("_no_retry", False)
        base, response = await super()._request(method, path_and_query, **kwargs)
        # 441 "miss token" / 401 "signature is invalid" can mean the cached
        # token expired or got revoked. Bootstrap a fresh one and retry once.
        if response.status_code in (401, 441) and not no_retry:
            logger.info(
                "[moviebox-bootstrap] got %d on %s — re-bootstrapping and retrying",
                response.status_code, path_and_query,
            )
            _invalidate_token()
            self._runtime_token = await _ensure_token()
            if self._runtime_token:
                base, response = await super()._request(method, path_and_query, **kwargs)
        return base, response


def make_client() -> _BootstrappingClient:
    if _MOVIEBOX_API_PROXY:
        return _BootstrappingClient(proxy=_MOVIEBOX_API_PROXY)
    return _BootstrappingClient()


__all__ = ["make_client"]
