"""Visitor stats endpoints.

`/api/stats/beat` is hit by every page every ~30s with a client-generated UUID;
first-time sids increment the cumulative total. `/api/stats/summary` is gated
behind `ADMIN_TOKEN` for the admin page. No PII is stored — just the UUID.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, Query, Response

from .. import stats

router = APIRouter()


@router.get("/stats/beat")
def beat(sid: str = Query(..., min_length=8, max_length=128)) -> Response:
    stats.record_beat(sid)
    return Response(status_code=204)


@router.get("/stats/summary")
def summary(x_admin_token: str | None = Header(default=None)) -> dict[str, int]:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    return stats.summary()
