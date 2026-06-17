"""Shared factory for the MovieBox v3 client.

The mobile-bff endpoints (search, item-details, /resource, /play-info,
/season-info) live on `api6.aoneroom.com` and friends. MovieBox blocks our
Fly Singapore egress on some of those — /resource and /play-info return
HTTP 406 'find no content' — so the structure endpoint and download list
go empty in prod. Routing those calls through the Cloudflare Worker
(``MOVIEBOX_PROXY_URL``) lets us bypass the block: the request URL path +
query (which is what the signature is computed over) is preserved
end-to-end, so MovieBox's signature check still passes.

This is the SAME Worker that fronts the H5 play domain (used by stream.py
directly for /subject/play). When ``MOVIEBOX_PROXY_URL`` is set, mobile-bff
calls go through it too; the Worker dispatches by URL prefix.

Set ``MOVIEBOX_API_PROXY`` for an httpx-style proxy (e.g. ``socks5://...``)
when you want to route the API at the transport level instead.
"""
from __future__ import annotations

import os

import httpx
from moviebox_api.v3.http_client import MovieBoxHttpClient

_MOVIEBOX_API_PROXY = os.environ.get("MOVIEBOX_API_PROXY", "").strip()
_PROXY_BASE = os.environ.get("MOVIEBOX_PROXY_URL", "").rstrip("/")
_PROXY_SECRET = os.environ.get("MOVIEBOX_PROXY_SECRET", "")


class _AuthInjectingClient(httpx.AsyncClient):
    """httpx client that injects the proxy auth secret on every request.

    The Cloudflare Worker requires ``X-Auth`` to match ``PROXY_SECRET``;
    moviebox-api's HTTP client builds requests without knowing about our
    proxy, so we splice the header in at transport time.
    """

    def __init__(self, *, auth_secret: str, **kwargs):
        super().__init__(**kwargs)
        self._auth_secret = auth_secret

    async def send(self, request, *args, **kwargs):
        if self._auth_secret and "X-Auth" not in request.headers:
            request.headers["X-Auth"] = self._auth_secret
        return await super().send(request, *args, **kwargs)


class _ProxiedMovieBoxClient(MovieBoxHttpClient):
    """MovieBoxHttpClient variant whose internal httpx client injects X-Auth.

    Python looks up dunder methods on the *type*, not the instance, so we can't
    just monkeypatch ``__aenter__`` on a bare client — we subclass instead."""

    async def __aenter__(self) -> "_ProxiedMovieBoxClient":
        self._client = _AuthInjectingClient(
            auth_secret=_PROXY_SECRET,
            timeout=self._timeout,
            follow_redirects=self._follow_redirects,
            **self._httpx_client_kwargs,
        )
        return self


def make_client() -> MovieBoxHttpClient:
    # When the Cloudflare Worker is configured, treat it as the only host in
    # the pool. The Worker forwards /wefeed-mobile-bff/* to the real API host
    # — signature is over path+query, not host, so this is transparent to
    # MovieBox's auth.
    if _PROXY_BASE:
        if _PROXY_SECRET:
            return _ProxiedMovieBoxClient(host_pool=[_PROXY_BASE])
        return MovieBoxHttpClient(host_pool=[_PROXY_BASE])

    if _MOVIEBOX_API_PROXY:
        return MovieBoxHttpClient(proxy=_MOVIEBOX_API_PROXY)
    return MovieBoxHttpClient()
