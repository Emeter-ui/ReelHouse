"""Trending / homepage feed cherry-picked from moviebox-fast.

Wraps MovieBox v3's Homepage endpoint, flattens its grouped sections into a
single list of subjects, and exposes a thin shape the frontend can consume
directly. Routed through the shared proxied client.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v3.constants import SubjectType, TabID

from ..cache import TTLCache
from ..moviebox_client import make_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Homepage shifts slowly; cache long enough to spare upstream while still
# refreshing within a session.
_cache = TTLCache(maxsize=32, ttl_seconds=10 * 60)


def _tab_for(type_: str) -> TabID:
    match type_.lower():
        case "movie" | "movies":
            return TabID.MOVIE
        case "series" | "tv" | "show" | "shows":
            return TabID.TV_SERIES
        case _:
            return TabID.MOVIE_TV


def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[-1] if parts else None


@router.get("/trending")
async def trending(
    type: str = Query("movie", description="movie | series | all"),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    cache_key = f"{type.lower()}:{page}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    tab = _tab_for(type)
    type_filter = None
    if type.lower() in ("movie", "movies"):
        type_filter = SubjectType.MOVIES
    elif type.lower() in ("series", "tv", "show", "shows"):
        type_filter = SubjectType.TV_SERIES

    async with make_client() as client:
        from moviebox_api.v3.core import Homepage

        homepage = Homepage(client_session=client)
        homepage._page_number = page
        homepage._tab_id = tab

        try:
            content = await homepage.get_content_model()
        except Exception:
            logger.exception("[trending] fetch failed for tab=%s page=%d", tab, page)
            raise HTTPException(status_code=502, detail={"error": "upstream"})

    # Flatten subjects across all sections, dedupe by subject_id, drop items
    # without an actual playable resource on MovieBox.
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for section in content.items:
        for subject in section.subjects:
            if not subject.has_resource:
                continue
            if type_filter is not None and subject.subject_type != type_filter:
                continue
            if subject.subject_id in seen:
                continue
            seen.add(subject.subject_id)
            results.append(
                {
                    "id": subject.subject_id,
                    "title": subject.title,
                    "year": subject.release_date.year if subject.release_date else None,
                    "poster": str(subject.cover.url),
                    "thumbnail": subject.cover.thumbnail,
                    "rating": subject.imdb_rating_value,
                    "description": subject.description,
                    "genres": subject.genre,
                    "country": subject.country_name,
                    "type": (
                        "movie" if subject.subject_type == SubjectType.MOVIES else "series"
                    ),
                    "page_url": str(subject.detail_url) if subject.detail_url else None,
                    "detail_path": _slug_from_url(
                        str(subject.detail_url) if subject.detail_url else None
                    ),
                }
            )

    payload = {
        "success": True,
        "results": results,
        "pagination": {"current_page": page, "tab": str(tab.value), "count": len(results)},
    }
    _cache.set(cache_key, payload)
    return payload
