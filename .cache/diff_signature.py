"""Decode the captured MovieBox request and compare its signed canonical
string against what the moviebox-api Python package would build.

Usage:
  cd /home/dave/Desktop/Dave-Projects/reelhouse
  backend/.venv/bin/python .cache/diff_signature.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CAPS = Path(__file__).parent / "captures.jsonl"


def header(headers: list[list[str]], name: str) -> str | None:
    name_l = name.lower()
    for k, v in headers:
        if k.lower() == name_l:
            return v
    return None


def find_first_subject_request(records: list[dict]) -> dict | None:
    for rec in records:
        if rec.get("kind") == "response":
            continue
        path = rec.get("path", "")
        if "/wefeed-mobile-bff/subject-api/" in path:
            return rec
    return None


def main() -> int:
    if not CAPS.exists():
        sys.exit(f"no capture file at {CAPS} — has the app made a request yet?")
    records = [json.loads(line) for line in CAPS.read_text().splitlines() if line.strip()]
    cap = find_first_subject_request(records)
    if cap is None:
        sys.exit(
            "no /wefeed-mobile-bff/subject-api/* request in capture yet. "
            "Open the patched MovieBox app and search for a title."
        )

    print(f"=== captured request ===")
    print(f"method:   {cap['method']}")
    print(f"url:      {cap['url']}")
    print(f"path:     {cap['path']}")
    print(f"body_len: {cap['body_len']}")
    print(f"body[:300]: {cap['body_text'][:300]!r}\n")

    print(f"=== headers (verbatim) ===")
    for k, v in cap["headers"]:
        print(f"  {k}: {v}")

    sig = header(cap["headers"], "x-tr-signature")
    client_token = header(cap["headers"], "x-client-token")
    auth = header(cap["headers"], "authorization")
    accept = header(cap["headers"], "accept")
    content_type = header(cap["headers"], "content-type")
    content_length = header(cap["headers"], "content-length")
    client_info = header(cap["headers"], "x-client-info")

    print(f"\n=== captured signed values ===")
    print(f"x-tr-signature: {sig}")
    print(f"x-client-token: {client_token}")
    print(f"authorization:  {auth and auth[:40]+'...'}")

    if not sig:
        print("ERROR: capture has no x-tr-signature header. Aborting diff.")
        return 1

    m = re.match(r"^(\d+)\|(\d+)\|(.+)$", sig)
    if not m:
        print(f"ERROR: x-tr-signature didn't parse: {sig!r}")
        return 1
    ts_str, ver, sig_b64 = m.groups()
    ts_ms = int(ts_str)
    print(f"  ts (captured signed time): {ts_ms}")
    print(f"  version marker:            {ver}")
    print(f"  signature b64:             {sig_b64}\n")

    # Build canonical-string that the Python package WOULD build for this same
    # request, using captured headers + body + timestamp.
    from moviebox_api.v3.crypto import (
        build_canonical_string,
        generate_x_tr_signature,
        b64_decode,
        b64_encode,
    )
    from moviebox_api.v3.constants import SECRET_KEY_DEFAULT, SECRET_KEY_ALT
    import hmac
    import hashlib

    body_bytes = bytes.fromhex(cap["body_b64"]) if cap["body_b64"] else b""
    body_str = body_bytes.decode("utf-8", errors="replace") if body_bytes else None

    canonical = build_canonical_string(
        cap["method"],
        accept or "",
        content_type or "",
        cap["url"],
        body_str,
        ts_ms,
    )
    print(f"=== Python-package canonical string (reconstructed) ===\n{canonical}\n")

    # Try BOTH keys and the version marker the capture uses.
    for label, secret in (("DEFAULT(76iRl...)", SECRET_KEY_DEFAULT), ("ALT(Xqn2...)", SECRET_KEY_ALT)):
        mac = hmac.new(b64_decode(secret), canonical.encode(), hashlib.md5).digest()
        local = b64_encode(mac)
        match = "✅ MATCH" if local == sig_b64 else "❌ no match"
        print(f"  key={label:24}  sig={local!r}   captured={sig_b64!r}  → {match}")

    # If neither matched, try SHA256 (sometimes used as a fallback algorithm).
    print()
    for label, secret in (("DEFAULT", SECRET_KEY_DEFAULT), ("ALT", SECRET_KEY_ALT)):
        mac = hmac.new(b64_decode(secret), canonical.encode(), hashlib.sha256).digest()
        local = b64_encode(mac)
        match = "✅ MATCH" if local == sig_b64 else "❌"
        print(f"  sha256 key={label} → {local!r}  {match}")

    print(
        "\nIf NO match: either the canonical string differs (compare line-by-line "
        "to what the Android app actually generates) or the secret key was rotated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
