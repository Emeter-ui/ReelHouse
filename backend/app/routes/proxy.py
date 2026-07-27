"""Byte-proxy a remote video/subtitle URL through the backend.

Used as the player's fallback `<source>` when a direct CDN URL fails the
HEAD CORS probe. Streams the response chunk-by-chunk and forwards Range
so seeking works.

For MovieBox's hakunaymatata.com CDNs we cannot fetch directly — the CDN
allowlists Referer (which the browser can't spoof) AND blocks datacenter
egress (so Render gets 403 even with the right Referer). We tunnel those
fetches through the Fly Singapore proxy's /cdn route, which runs from a
region the CDN trusts and injects the Referer for us.
"""
from __future__ import annotations

import mimetypes
import os
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

router = APIRouter()

# Optional residential proxy (Webshare/BrightData/etc.) for CDN byte fetches.
# When set, all upstream fetches from /proxy and /dash-manifest route through
# it — MovieBox has periodically block-listed every datacenter IP range we've
# used (CF Workers, Fly, Railway multi-region), and only residential IPs
# reliably reach the CDN. Format: http://user:pass@host:port
_RESIDENTIAL_PROXY = os.environ.get("RESIDENTIAL_PROXY_URL", "").strip() or None

# Keep one client alive for connection pooling. Routes through the residential
# proxy when configured, else direct.
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=None),
    follow_redirects=True,
    proxy=_RESIDENTIAL_PROXY,
)

UPSTREAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}

# Headers we forward back to the browser.
PASS_THROUGH_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "last-modified",
    "etag",
    "cache-control",
}

# Cloudflare Worker that tunnels hakunaymatata.com CDN bytes for us. The
# CDN IP-blocks Fly's egress even with the right Referer, so manifest +
# segment + MP4 fetches have to detour through a non-Fly host. The Worker
# is on CF's IPs, which the CDN trusts. Configured by `MOVIEBOX_PROXY_URL`
# (the only purpose this env var still serves — H5 and mobile-bff API
# calls now go direct from Fly).
_FLY_PROXY_BASE = os.environ.get("MOVIEBOX_PROXY_URL", "").rstrip("/")
_FLY_PROXY_SECRET = os.environ.get("MOVIEBOX_PROXY_SECRET", "")
_FLY_TUNNELED_HOST_SUFFIX = ".hakunaymatata.com"

# The mobile download CDN (`bcdn.*`) has an nginx anti-abuse layer in front of
# it that rejects any request with a Referer OR a browser User-Agent — the
# signed URL alone authenticates, and only the MovieBox mobile app's UA is
# allowed through. Confirmed empirically: Chrome/Firefox/Safari UAs → 428;
# MovieBox iOS / okhttp UAs → 200. The play CDN (`bcdnxw.*`) behaves
# oppositely (needs browser UA + Referer=netfilm.world), so this rule is
# scoped to the download host.
_MOBILE_HOSTS = frozenset({"bcdn.hakunaymatata.com"})
# UA of the real MovieBox iOS app — the anti-abuse layer allowlists this and
# okhttp/*. If MovieBox tightens the check further (e.g. requires the exact
# current app version), rev this string.
_MOBILE_UA = "MovieBox/8.0.1 (iPhone; iOS 16.5; Scale/3.00)"


def _is_mobile_host(host: str) -> bool:
    return host.lower() in _MOBILE_HOSTS


def _is_allowed_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    # Don't ever proxy back to ourselves or to private hosts.
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    return True


def _should_tunnel_via_fly(host: str) -> bool:
    """Route CDN bytes through the CF Worker when the backend's own egress
    is blocked by the CDN. Historically Render/Fly-datacenter IPs were 403'd.

    Overrides (in order):
      1. Residential proxy configured → skip the Worker entirely. The httpx
         client will route the direct fetch through the residential proxy,
         which is the whole point of having one.
      2. `bcdn.*` (mobile download CDN) → skip the Worker even without a
         residential proxy. MovieBox's anti-abuse returns 427 to Cloudflare
         Worker IPs even for correctly-signed mobile-UA requests."""
    if _RESIDENTIAL_PROXY:
        return False
    if _is_mobile_host(host):
        return False
    return bool(_FLY_PROXY_BASE) and host.lower().endswith(_FLY_TUNNELED_HOST_SUFFIX)


@router.api_route("/proxy", methods=["GET", "HEAD"])
async def proxy(
    url: str,
    request: Request,
    referer: str | None = None,
    dl: str | None = None,
    cookie: str | None = None,
) -> StreamingResponse:
    if not _is_allowed_target(url):
        raise HTTPException(status_code=400, detail={"error": "invalid url"})

    parsed = urlparse(url)
    use_fly_tunnel = _should_tunnel_via_fly(parsed.hostname or "")

    mobile_host = _is_mobile_host(parsed.hostname or "")

    if use_fly_tunnel:
        # Hand off to the Fly proxy: it injects Referer + fetches from a
        # CDN-allowed region. We just forward Range and the auth secret.
        upstream_url = f"{_FLY_PROXY_BASE}/cdn?url={quote(url, safe='')}"
        if mobile_host:
            # bcdn.* requires no-referer + MovieBox UA. Worker handles both
            # when it sees this flag; see worker/moviebox-proxy.js handleCdn.
            upstream_url += "&no_referer=1"
        else:
            ref = referer if referer and urlparse(referer).scheme in ("http", "https") else "https://netfilm.world/"
            upstream_url += f"&referer={quote(ref, safe='')}"
        if cookie:
            upstream_url += f"&cookie={quote(cookie, safe='')}"
        upstream_headers: dict[str, str] = {
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if _FLY_PROXY_SECRET:
            upstream_headers["X-Auth"] = _FLY_PROXY_SECRET
    else:
        upstream_url = url
        if mobile_host:
            # `bcdn.*` (mobile download CDN): anti-abuse allowlists mobile-app
            # UAs only and rejects any request that carries a Referer. Set the
            # MovieBox iOS UA and omit Referer/Origin; the signed URL
            # authenticates on its own.
            upstream_headers = {
                "User-Agent": _MOBILE_UA,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            }
        else:
            upstream_headers = dict(UPSTREAM_HEADERS)
            # Most CDNs allowlist Referer against an originating page; honour
            # the caller hint when given, else default to the URL's own host.
            if referer and urlparse(referer).scheme in ("http", "https"):
                upstream_headers["Referer"] = referer
                ref = urlparse(referer)
                upstream_headers["Origin"] = f"{ref.scheme}://{ref.netloc}"
            else:
                upstream_headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
                upstream_headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
        # CloudFront signed cookies are how MovieBox gates DASH manifests +
        # segments. The browser can't set cross-origin cookies via JS, so the
        # caller passes the cookie string here and we forward it upstream.
        if cookie:
            upstream_headers["Cookie"] = cookie

    # Forward Range from the browser so video seeking works (in both modes).
    incoming_range = request.headers.get("range")
    if incoming_range:
        upstream_headers["Range"] = incoming_range

    req = _client.build_request(request.method, upstream_url, headers=upstream_headers)
    upstream = await _client.send(req, stream=True)

    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(
            status_code=upstream.status_code,
            detail={"error": "upstream error"},
        )

    response_headers: dict[str, str] = {}
    for k, v in upstream.headers.items():
        if k.lower() in PASS_THROUGH_RESPONSE_HEADERS:
            response_headers[k] = v
    response_headers.setdefault("accept-ranges", "bytes")
    # Discourage buffering on Render/Nginx to keep the stream flowing.
    response_headers["X-Accel-Buffering"] = "no"

    media_type = upstream.headers.get("content-type", "application/octet-stream")
    
    # If 'dl' is set, force an attachment download with that filename and 
    # use application/octet-stream to discourage the browser from playing it.
    if dl:
        # Ensure the filename is safe for headers
        safe_dl = dl.replace('"', "'")
        response_headers["Content-Disposition"] = f'attachment; filename="{safe_dl}"'
        media_type = "application/octet-stream"
    
    # If content-type is missing or generic, try guessing from URL or forcing video.
    elif media_type == "application/octet-stream" or not media_type:
        guessed, _ = mimetypes.guess_type(url)
        if guessed:
            media_type = guessed
        elif ".mp4" in url.lower():
            media_type = "video/mp4"
        elif ".mkv" in url.lower():
            media_type = "video/x-matroska"
        elif ".m3u8" in url.lower():
            media_type = "application/x-mpegURL"

    async def iter_bytes():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        iter_bytes(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=media_type,
    )


@router.get("/dash-manifest")
async def dash_manifest(
    url: str = Query(...),
    cookie: str | None = Query(default=None),
    referer: str | None = Query(default=None),
) -> Response:
    """Fetch a MovieBox DASH manifest, inject a ``<BaseURL>`` so segments
    resolve to absolute CDN URLs, return the rewritten XML.

    Why this exists: MovieBox's manifests don't declare a `<BaseURL>` and
    their `SegmentTemplate` paths are relative (``init-stream0.m4s``,
    ``chunk-stream0-00001.m4s``). dash.js would resolve those against the
    document URL — which, when the manifest is fetched through our generic
    `/api/proxy`, is the proxy URL itself, producing nonsense segment URLs.
    Injecting `<BaseURL>` at the CDN directory makes segments absolute again;
    the player's request interceptor then routes them through `/api/proxy`
    with the same signed cookie.
    """
    if not _is_allowed_target(url):
        raise HTTPException(status_code=400, detail={"error": "invalid url"})
    parsed = urlparse(url)

    # Same tunnel selection as /proxy — datacenter egress is 403'd on the CDN.
    use_fly_tunnel = _should_tunnel_via_fly(parsed.hostname or "")
    if use_fly_tunnel:
        ref = referer if referer and urlparse(referer).scheme in ("http", "https") else "https://netfilm.world/"
        upstream_url = (
            f"{_FLY_PROXY_BASE}/cdn"
            f"?url={quote(url, safe='')}"
            f"&referer={quote(ref, safe='')}"
        )
        if cookie:
            upstream_url += f"&cookie={quote(cookie, safe='')}"
        upstream_headers: dict[str, str] = {
            "Accept": "application/dash+xml,application/xml,*/*",
            "Accept-Encoding": "identity",
        }
        if _FLY_PROXY_SECRET:
            upstream_headers["X-Auth"] = _FLY_PROXY_SECRET
    else:
        upstream_url = url
        upstream_headers = dict(UPSTREAM_HEADERS)
        upstream_headers["Referer"] = (
            referer if referer and urlparse(referer).scheme in ("http", "https")
            else f"{parsed.scheme}://{parsed.netloc}/"
        )
        upstream_headers["Origin"] = (
            f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
            if referer else f"{parsed.scheme}://{parsed.netloc}"
        )
        if cookie:
            upstream_headers["Cookie"] = cookie

    try:
        r = await _client.get(upstream_url, headers=upstream_headers)
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"error": "upstream", "message": str(exc)})
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail={"error": "upstream error"})

    xml = r.text
    # The CDN directory the manifest lives in — segments resolve against this.
    base_dir = url.rsplit("/", 1)[0] + "/"
    # Insert <BaseURL> as the first child of every <Period>. dash.js prefers
    # Period-level BaseURL over MPD-level (per spec) — using Period scope keeps
    # the injection safe even if the manifest already had a top-level BaseURL.
    base_tag = f"<BaseURL>{base_dir}</BaseURL>"
    injected = xml.replace("<Period", f"{base_tag}<Period", 1)
    # Above only injects before the first <Period>, but as a sibling — that's
    # outside the Period element. Move it inside instead.
    if base_tag + "<Period" in injected:
        # Pull the BaseURL line back out and inject after `>` of the Period tag.
        injected = injected.replace(base_tag + "<Period", "<Period")
        # Now find the closing `>` of the first <Period ...> and insert the tag.
        idx = injected.find("<Period")
        if idx != -1:
            close = injected.find(">", idx)
            if close != -1:
                injected = injected[: close + 1] + base_tag + injected[close + 1 :]

    return Response(
        content=injected,
        media_type="application/dash+xml",
        headers={"Cache-Control": "no-store"},
    )

