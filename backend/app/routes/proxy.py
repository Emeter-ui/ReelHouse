"""Byte-proxy a remote video/subtitle URL through the backend.

Used as the player's fallback `<source>` when a direct CDN URL fails the
HEAD CORS probe. Streams the response chunk-by-chunk and forwards Range
so seeking works.
"""
from __future__ import annotations

import mimetypes
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

# Keep one client alive for connection pooling.
_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None), follow_redirects=True)

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


@router.api_route("/proxy", methods=["GET", "HEAD"])
async def proxy(
    url: str,
    request: Request,
    referer: str | None = None,
    dl: str | None = None,
) -> StreamingResponse:
    if not _is_allowed_target(url):
        raise HTTPException(status_code=400, detail={"error": "invalid url"})

    parsed = urlparse(url)
    upstream_headers = dict(UPSTREAM_HEADERS)
    # MovieBox's CDN allowlists Referer against its play domain, so prefer the
    # caller-supplied hint when present. Fall back to the URL's own host for
    # everything else (subtitles etc.).
    if referer and urlparse(referer).scheme in ("http", "https"):
        upstream_headers["Referer"] = referer
        ref = urlparse(referer)
        upstream_headers["Origin"] = f"{ref.scheme}://{ref.netloc}"
    else:
        upstream_headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        upstream_headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"

    # Forward Range from the browser so video seeking works.
    incoming_range = request.headers.get("range")
    if incoming_range:
        upstream_headers["Range"] = incoming_range

    req = _client.build_request(request.method, url, headers=upstream_headers)
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

    media_type = upstream.headers.get("content-type", "application/octet-stream")
    
    # If 'dl' is set, force an attachment download with that filename and 
    # use application/octet-stream to discourage the browser from playing it.
    if dl:
        # Ensure the filename is safe for headers
        safe_dl = dl.replace('"', "'")
        response_headers["Content-Disposition"] = f'attachment; filename="{safe_dl}"'
        media_type = "application/octet-stream"
    
    # If content-type is missing or generic, try guessing from URL.
    elif media_type == "application/octet-stream" or not media_type:
        guessed, _ = mimetypes.guess_type(url)
        if guessed:
            media_type = guessed

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

