"""Reelhouse residential-IP proxy for MovieBox CDN bytes.

Runs on a machine whose outbound IP isn't on MovieBox's block list (typically
a home ISP or non-cloud VM). Exposes the same `/cdn` API as
`worker/moviebox-proxy.js`, so Railway can tunnel every CDN fetch through here
by setting `MOVIEBOX_PROXY_URL` to this server's public URL (via Cloudflare
Tunnel or similar).

Auth: shared secret via `X-Auth` header. Set `PROXY_SECRET` to match Railway's
`MOVIEBOX_PROXY_SECRET`.

Run:
    export PROXY_SECRET=<paste secret>
    python3 proxy_server.py
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

app = FastAPI(title="reelhouse-local-proxy")

_PROXY_SECRET = os.environ.get("PROXY_SECRET", "").strip()

# UA/Referer combinations MovieBox's CDN accepts, per host.
# bcdn.* (mobile download CDN): mobile-app UA, no Referer.
# bcdnxw.* (play CDN):          browser UA + Referer=netfilm.world.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_MOBILE_UA = "MovieBox/8.0.1 (iPhone; iOS 16.5; Scale/3.00)"

# Reject anything not on the MovieBox CDN so this isn't an open relay.
_ALLOWED_HOST_SUFFIX = ".hakunaymatata.com"

_PORT = int(os.environ.get("PORT", "8888"))

_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=None),
    follow_redirects=True,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/cdn", methods=["GET", "HEAD"])
async def cdn(
    request: Request,
    url: str = Query(...),
    referer: str | None = Query(default=None),
    cookie: str | None = Query(default=None),
    no_referer: str | None = Query(default=None),
):
    if _PROXY_SECRET and request.headers.get("X-Auth") != _PROXY_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host.endswith(_ALLOWED_HOST_SUFFIX):
        raise HTTPException(status_code=400, detail="host not allowed")

    skip_ref = no_referer == "1"

    headers: dict[str, str] = {
        "User-Agent": _MOBILE_UA if skip_ref else _BROWSER_UA,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    if not skip_ref:
        ref = referer if referer and urlparse(referer).scheme in ("http", "https") else "https://netfilm.world/"
        headers["Referer"] = ref
        origin = urlparse(ref)
        headers["Origin"] = f"{origin.scheme}://{origin.netloc}"
    if cookie:
        headers["Cookie"] = cookie
    # Forward Range so video seeking works end-to-end.
    incoming_range = request.headers.get("range")
    if incoming_range:
        headers["Range"] = incoming_range

    req = _client.build_request(request.method, url, headers=headers)
    upstream = await _client.send(req, stream=True)

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        return Response(
            content=body,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/plain"),
            headers={"access-control-allow-origin": "*"},
        )

    forward: dict[str, str] = {"access-control-allow-origin": "*"}
    for name in ("content-type", "content-range", "content-length", "accept-ranges", "etag", "last-modified"):
        v = upstream.headers.get(name)
        if v:
            forward[name] = v

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=forward,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
