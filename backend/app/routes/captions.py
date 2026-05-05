"""Fetch a subtitle URL and serve it as WebVTT.

The native HTML5 `<track>` element only renders WebVTT. MovieBox's caption
URLs are SubRip (.srt). This endpoint fetches the upstream file and converts
on the fly so the browser's built-in caption menu works.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Response

router = APIRouter()

_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# SRT timecode "HH:MM:SS,mmm --> HH:MM:SS,mmm". WebVTT wants "." not ",".
_SRT_TIMECODE_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}),(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}),(\d{3})"
)


def _srt_to_vtt(srt: str) -> str:
    # Drop UTF-8 BOM if present.
    if srt.startswith("﻿"):
        srt = srt[1:]
    # Convert timecodes.
    body = _SRT_TIMECODE_RE.sub(r"\1.\2 --> \3.\4", srt)
    # Normalize line endings.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return f"WEBVTT\n\n{body}"


def _is_allowed_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    return True


@router.get("/captions")
async def captions(url: str) -> Response:
    if not _is_allowed_target(url):
        raise HTTPException(status_code=400, detail={"error": "invalid url"})

    try:
        r = await _client.get(url, headers={"User-Agent": _BROWSER_UA, "Accept": "*/*"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}") from exc

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail="upstream returned error")

    text = r.text
    upstream_ct = (r.headers.get("content-type") or "").lower()
    looks_like_vtt = "vtt" in upstream_ct or text.lstrip().upper().startswith("WEBVTT")

    body = text if looks_like_vtt else _srt_to_vtt(text)

    return Response(
        content=body,
        media_type="text/vtt; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )
