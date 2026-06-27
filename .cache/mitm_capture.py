"""mitmdump addon: capture MovieBox /subject-api/* requests verbatim.

Run via:
  cd /home/dave/Desktop/Dave-Projects/reelhouse
  backend/.venv/bin/mitmdump --listen-host 0.0.0.0 --listen-port 8080 \
      -s .cache/mitm_capture.py

When the phone hits api6.aoneroom.com (or any *.aoneroom.com /wefeed-mobile-bff/*),
the request is appended to .cache/captures.jsonl with the full canonical-string
inputs needed to verify the signature.

Make a search in the MovieBox app on your phone — the search request should be
captured and logged with [CAPTURED] in the terminal.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from mitmproxy import ctx, http

OUT = Path(__file__).parent / "captures.jsonl"
COUNTER = {"n": 0}


def _wanted(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    path = flow.request.path
    if not host.endswith("aoneroom.com") and not host.endswith("inmoviebox.com"):
        return False
    return "/wefeed-mobile-bff/" in path or "/wefeed-h5api-bff/" in path or "/wefeed-h5-bff/" in path


def request(flow: http.HTTPFlow) -> None:
    if not _wanted(flow):
        return
    body_bytes = flow.request.content or b""
    rec = {
        "ts_client_ms": int(time.time() * 1000),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "path": flow.request.path,
        "headers": [list(h) for h in flow.request.headers.items()],
        "body_len": len(body_bytes),
        "body_b64": body_bytes.hex(),  # safer than raw for binary
        "body_text": (body_bytes.decode("utf-8", errors="replace")[:8192]
                      if body_bytes else ""),
    }
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    COUNTER["n"] += 1
    ctx.log.info(
        f"[CAPTURED #{COUNTER['n']}] {rec['method']} {rec['path']}  "
        f"body={rec['body_len']}b  → {OUT.name}"
    )


def response(flow: http.HTTPFlow) -> None:
    if not _wanted(flow):
        return
    if flow.response is None:
        return
    resp_body = flow.response.content or b""
    rec = {
        "ts_client_ms": int(time.time() * 1000),
        "kind": "response",
        "url": flow.request.pretty_url,
        "status": flow.response.status_code,
        "resp_headers": [list(h) for h in flow.response.headers.items()],
        "resp_body_text": resp_body.decode("utf-8", errors="replace")[:4096],
    }
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def load(loader):
    ctx.log.info(f"capture-addon ready — writing to {OUT}")
