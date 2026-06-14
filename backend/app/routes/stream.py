"""Resolve a TMDB title to a moviebox stream URL + qualities + captions.

Hits MovieBox's web `/subject/play` endpoint (the same one the official h5
player and third-party sites like mymuvies use). Avoids `/subject-api/resource`
because that's the mobile download endpoint — its URLs are HEVC-dominant and
not designed for browser `<video>`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from curl_cffi.requests import AsyncSession
from fastapi import APIRouter, HTTPException, Query
from moviebox_api.v1.constants import SubjectType
from moviebox_api.v3.constants import ResolutionType
from moviebox_api.v3.core import DownloadableVideoFilesDetail, ItemDetails, Search
from moviebox_api.v3.http_client import MovieBoxHttpClient
from moviebox_api.v3.models.downloadables import VideoFileMetadata
from moviebox_api.v3.urls import EXT_CAPTIONS_PATH, PLAY_INFO_PATH

from .. import fzmovies
from ..cache import TTLCache
from ..config import get_settings
from ..matching import Candidate, best_match
from ..moviebox_client import make_client

logger = logging.getLogger(__name__)

# Impersonate real Chrome's TLS fingerprint so MovieBox doesn't flag the
# request as bot traffic from the (datacenter) backend host.
_IMPERSONATE = "chrome124"

# Cloudflare Worker that fronts the H5 play domain. MovieBox IP-blocks our
# Render egress on this domain; Worker runs on Cloudflare IPs and forwards
# with the Referer + uuid cookie MovieBox needs. When unset, we hit MovieBox
# directly (works in local dev where the host isn't blocked).
_PROXY_BASE = os.environ.get("MOVIEBOX_PROXY_URL", "").rstrip("/")
_PROXY_SECRET = os.environ.get("MOVIEBOX_PROXY_SECRET", "")

router = APIRouter()

# Play URLs are short-lived signed CDN links. Cache long enough to absorb
# pause/refresh within a session, short enough that we re-sign before the
# upstream signature expires.
_cache = TTLCache(maxsize=512, ttl_seconds=3 * 60)

# Full per-subject file set. The resource endpoint ignores se/ep filters, so we
# must pull every page to resolve one episode — caching it per subject means a
# series' episodes (and the structure endpoint, which warms this on page load)
# share one fetch instead of re-paging on every click. Holds signed download
# URLs, so kept as short-lived as the play-URL cache above.
_all_files_cache = TTLCache(maxsize=256, ttl_seconds=3 * 60)
# Pages fetched concurrently per subject — fast without hammering MovieBox.
_MAX_PAGE_CONCURRENCY = 6

# title→subject match is stable; cache it so the structure call and the
# subsequent play/download resolve don't both repeat search + item-details.
_match_cache = TTLCache(maxsize=1024, ttl_seconds=3600)

# TMDB/AniList alt titles change rarely; cache for a day to cap fallback latency.
_alt_titles_cache = TTLCache(maxsize=2048, ttl_seconds=24 * 3600)
_http_client: httpx.AsyncClient | None = None

# Country codes whose alt titles are most likely to match MovieBox's English-
# titled catalogue. Other locales (KR, JP, RU, ...) usually carry translations
# that won't fuzz-match and would just waste MovieBox API calls.
_EN_COUNTRIES = frozenset({"US", "GB", "AU", "CA", "IE", "NZ"})

# Hard cap so an outlier title with dozens of regional aliases doesn't trigger
# dozens of MovieBox roundtrips on every miss.
_ALT_TITLES_MAX_RETRIES = 8

_ANILIST_URL = "https://graphql.anilist.co"
_ANILIST_SYNONYMS_QUERY = """
query ($id: Int!) {
  Media(id: $id, type: ANIME) {
    title { romaji english native }
    synonyms
  }
}
"""


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    return _http_client


async def _fetch_alternative_titles(tmdb_id: int, is_series: bool) -> list[str]:
    """Return TMDB's alternative titles for a tmdb_id, English-country first.
    Used to retry MovieBox resolution when the primary TMDB title doesn't
    fuzz-match (e.g. TMDB calls it 'Captain America: Brave New World',
    MovieBox calls it 'Captain America 4')."""
    kind = "tv" if is_series else "movie"
    cache_key = f"{kind}:{tmdb_id}"
    cached = _alt_titles_cache.get(cache_key)
    if cached is not None:
        return cached

    settings = get_settings()
    url = f"{settings.tmdb_base_url}/{kind}/{tmdb_id}/alternative_titles"
    try:
        r = await _get_http_client().get(
            url, params={"api_key": settings.tmdb_api_key}
        )
        r.raise_for_status()
        payload = r.json() or {}
    except Exception as e:
        logger.warning(
            "[alt_titles] tmdb_id=%s kind=%s fetch failed: %s", tmdb_id, kind, e
        )
        _alt_titles_cache.set(cache_key, [])
        return []

    # Movies key on "titles", TV on "results".
    items = payload.get("titles" if not is_series else "results") or []
    en, other = [], []
    for t in items:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        (en if t.get("iso_3166_1") in _EN_COUNTRIES else other).append(title)

    out: list[str] = []
    seen: set[str] = set()
    for t in en + other:
        norm = t.casefold()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(t)

    _alt_titles_cache.set(cache_key, out)
    return out


async def _fetch_anilist_synonyms(anilist_id: int) -> list[str]:
    """Return AniList's title.english/romaji/native + synonyms for a media id.
    Anime equivalent of `_fetch_alternative_titles` — MovieBox indexes anime
    under their English release names, but if the frontend sent romaji and that
    misses, the English title (or a synonym) usually doesn't."""
    cache_key = f"anilist:{anilist_id}"
    cached = _alt_titles_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        r = await _get_http_client().post(
            _ANILIST_URL,
            json={
                "query": _ANILIST_SYNONYMS_QUERY,
                "variables": {"id": anilist_id},
            },
        )
        r.raise_for_status()
        media = ((r.json() or {}).get("data") or {}).get("Media") or {}
    except Exception as e:
        logger.warning(
            "[alt_titles] anilist_id=%s fetch failed: %s", anilist_id, e
        )
        _alt_titles_cache.set(cache_key, [])
        return []

    titles = media.get("title") or {}
    # English first (most likely to match MovieBox), then romaji, then native,
    # then community-submitted synonyms.
    raw = [
        titles.get("english"),
        titles.get("romaji"),
        titles.get("native"),
        *(media.get("synonyms") or []),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not t:
            continue
        norm = t.casefold().strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(t)

    _alt_titles_cache.set(cache_key, out)
    return out


async def _resolve_with_alt_titles(
    title: str,
    year: int | None,
    subject_type: SubjectType,
    *,
    tmdb_id: int | None = None,
    anilist_id: int | None = None,
    season: int | None = None,
    episode: int | None = None,
) -> dict[str, Any] | None:
    """Run `_resolve`; on miss, retry with TMDB alt titles (for tmdb_id) or
    AniList synonyms (for anilist_id). At most one of the two ids should be
    set per request; if both are present, TMDB wins."""
    resolved = await _resolve(title, year, subject_type, season=season, episode=episode)
    if resolved is not None:
        return resolved

    if tmdb_id is not None:
        is_series = subject_type != SubjectType.MOVIES
        alts = await _fetch_alternative_titles(tmdb_id, is_series=is_series)
        label = f"tmdb:{'tv' if is_series else 'movie'}"
    elif anilist_id is not None:
        alts = await _fetch_anilist_synonyms(anilist_id)
        label = "anilist"
    else:
        return None

    primary_norm = title.casefold()
    tried = 0
    for alt in alts:
        if alt.casefold() == primary_norm:
            continue
        tried += 1
        if tried > _ALT_TITLES_MAX_RETRIES:
            break
        logger.info("[alt_titles] retry kind=%s alt=%r", label, alt)
        resolved = await _resolve(
            alt, year, subject_type, season=season, episode=episode
        )
        if resolved is not None:
            return resolved
    return None


async def _iter_titles_with_alts(
    title: str,
    *,
    tmdb_id: int | None,
    anilist_id: int | None,
    is_series: bool,
):
    """Yield the primary title, then its alt titles (TMDB) or synonyms
    (AniList), deduped against the primary and capped at the retry limit.
    Shared by the stream resolver path and the structure matcher so both
    explore identical title variations."""
    yield title
    if tmdb_id is not None:
        alts = await _fetch_alternative_titles(tmdb_id, is_series=is_series)
    elif anilist_id is not None:
        alts = await _fetch_anilist_synonyms(anilist_id)
    else:
        return
    primary_norm = title.casefold()
    tried = 0
    for alt in alts:
        if alt.casefold() == primary_norm:
            continue
        tried += 1
        if tried > _ALT_TITLES_MAX_RETRIES:
            break
        yield alt


async def _match_query(
    client: MovieBoxHttpClient,
    query: str,
    year: int | None,
    subject_type: SubjectType,
) -> tuple[str, str | None] | None:
    """Search MovieBox for `query`, pick the best match, and resolve the dub
    redirect — returning (target_subject_id, detail_path). Positive results are
    cached (title→subject is stable) so repeated lookups for the same title skip
    the search + item-details round-trips. Negative results aren't cached (so
    alt-title retries still happen)."""
    ck = f"{int(subject_type)}:{query.casefold()}:{year or ''}"
    cached = _match_cache.get(ck)
    if cached is not None:
        return cached
    candidates = await _search_candidates(client, query, subject_type)
    match = best_match(query, year, candidates)
    if match is None:
        return None
    target = await _resolve_target(client, match.subject_id, match.detail_path)
    _match_cache.set(ck, target)
    return target


async def _match_target_subject(
    client: MovieBoxHttpClient,
    title: str,
    year: int | None,
    subject_type: SubjectType,
    *,
    tmdb_id: int | None = None,
    anilist_id: int | None = None,
) -> tuple[str, str | None] | None:
    """Match (title, year) to a MovieBox subject — retrying with alt titles and
    resolving the dub redirect — and return (target_subject_id, detail_path).

    This is the *matching half* of `_resolve`, factored out so the structure
    endpoint lands on the exact same subject the stream resolver will, keeping
    their season/episode numbering in lockstep."""
    is_series = subject_type != SubjectType.MOVIES
    async for query in _iter_titles_with_alts(
        title, tmdb_id=tmdb_id, anilist_id=anilist_id, is_series=is_series
    ):
        target = await _match_query(client, query, year, subject_type)
        if target is not None:
            return target
    return None


async def _empty_meta() -> list[dict[str, Any]]:
    """Awaitable empty episode-meta list — lets the structure endpoint gather
    the TMDB fetch unconditionally even when there's no tmdb_id (anime)."""
    return []


async def _fetch_tmdb_episode_meta(tmdb_id: int) -> list[dict[str, Any]]:
    """Flat, in-order list of TMDB episode metadata across the real seasons
    (season_number > 0). Index i is the i-th episode of the whole series, which
    is what the structure aligner maps onto MovieBox's linear episode order."""
    settings = get_settings()
    base = settings.tmdb_base_url
    params = {"api_key": settings.tmdb_api_key}
    client = _get_http_client()
    try:
        r = await client.get(f"{base}/tv/{tmdb_id}", params=params)
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        logger.warning("[structure] tmdb tv/%s fetch failed: %s", tmdb_id, e)
        return []

    season_nums = sorted(
        s.get("season_number")
        for s in (data.get("seasons") or [])
        if (s.get("season_number") or 0) > 0
    )

    async def fetch_season(sn: int) -> list[dict[str, Any]]:
        try:
            r = await client.get(f"{base}/tv/{tmdb_id}/season/{sn}", params=params)
            r.raise_for_status()
            return (r.json() or {}).get("episodes") or []
        except Exception:
            return []

    # Seasons are independent — fetch them concurrently. gather preserves order,
    # so the flattened list stays in season → episode order.
    season_eps = await asyncio.gather(*(fetch_season(sn) for sn in season_nums))
    out: list[dict[str, Any]] = []
    for eps in season_eps:
        for e in sorted(eps, key=lambda e: e.get("episode_number") or 0):
            out.append(
                {
                    "name": e.get("name"),
                    "still_path": e.get("still_path"),
                    "overview": e.get("overview"),
                    "air_date": e.get("air_date"),
                    "runtime": e.get("runtime"),
                }
            )
    return out


def _build_structure(
    season_map: dict[int, list[int]], ep_meta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Combine MovieBox's authoritative season→episodes map with a flat,
    in-order list of source (TMDB) episode metadata.

    Episodes keep MovieBox's exact (season, episode) numbering. Names are
    attached by GLOBAL LINEAR position — the i-th MovieBox episode across all
    seasons takes the i-th source episode's name — which is what bridges
    cours/season splits (e.g. MovieBox Frieren S2E1 == global #29 == TMDB
    S1E29). Where no source episode lines up, the name falls back to
    'Episode N'."""
    seasons_out: list[dict[str, Any]] = []
    linear = 0
    for se in sorted(season_map):
        eps_out: list[dict[str, Any]] = []
        for ep in sorted(season_map[se]):
            meta = ep_meta[linear] if linear < len(ep_meta) else {}
            name = (meta.get("name") or "").strip() if meta else ""
            eps_out.append(
                {
                    "ep": ep,
                    "name": name or f"Episode {ep}",
                    "still_path": meta.get("still_path") if meta else None,
                    "overview": meta.get("overview") if meta else None,
                    "air_date": meta.get("air_date") if meta else None,
                    "runtime": meta.get("runtime") if meta else None,
                }
            )
            linear += 1
        seasons_out.append({"se": se, "episodes": eps_out})
    return seasons_out


_PLAY_DOMAIN_FALLBACK = "https://h5.aoneroom.com"
_PLAY_DOMAIN_DISCOVERY = (
    "https://h5-api.aoneroom.com/wefeed-h5api-bff/media-player/get-domain"
)
_PLAY_PATH = "/wefeed-h5api-bff/subject/play"
_DOWNLOAD_PATH = "/wefeed-h5api-bff/subject/download"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_X_CLIENT_INFO = '{"timezone":"Africa/Nairobi"}'

# A UUID-shaped cookie satisfies MovieBox's anti-scrape session check.
# Value doesn't have to be registered — just present and well-formed.
_SESSION_COOKIES = {"uuid": "d8c3539e-2e46-4000-af20-7046a856e30a"}


def _cache_key(
    source_id: int | str | None,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
) -> str:
    # Anime callers (AniList) have no tmdb_id — fall back to title+year so
    # cache hits still happen across repeated lookups.
    base = source_id if source_id is not None else f"{title.casefold()}|{year or ''}"
    return f"{base}:{season or ''}:{episode or ''}"


def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[-1] if parts else None


async def _search_candidates(
    client: MovieBoxHttpClient, query: str, subject_type: SubjectType
) -> list[Candidate]:
    search = Search(client_session=client, query=query, subject_type=subject_type)
    try:
        result = await search.get_content_model()
    except Exception:
        return []

    out: list[Candidate] = []
    for item in result.items:
        if not item.has_resource:
            continue
        year = item.release_date.year if item.release_date else None
        out.append(
            Candidate(
                subject_id=item.subject_id,
                title=item.title,
                year=year,
                detail_path=_slug_from_url(
                    str(item.detail_url) if item.detail_url else None
                ),
            )
        )
    return out


async def _resolve_target(
    client: MovieBoxHttpClient, subject_id: str, fallback_detail_path: str | None
) -> tuple[str, str | None]:
    # MovieBox indexes localized dubs (Hindi, Tamil, etc.) under separate
    # subject_ids and often ranks them ahead of the English original in search.
    # Redirect to the Original dub and use its canonical detail_path slug for
    # the play Referer.
    try:
        details = await ItemDetails(client_session=client).get_content_model(subject_id)
    except Exception:
        return subject_id, fallback_detail_path

    target_id = subject_id
    for dub in details.dubs:
        if dub.original:
            target_id = dub.subject_id
            break

    if target_id != subject_id:
        try:
            details = await ItemDetails(client_session=client).get_content_model(target_id)
        except Exception:
            return target_id, fallback_detail_path

    target_slug = _slug_from_url(
        str(details.detail_url) if details.detail_url else None
    )
    return target_id, target_slug or fallback_detail_path


async def _resolve_play_domain(client: AsyncSession) -> str:
    try:
        r = await client.get(
            _PLAY_DOMAIN_DISCOVERY,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "application/json",
                "X-Client-Info": _X_CLIENT_INFO,
                "X-Client-Type": "h5",
            },
            timeout=10,
        )
        if r.status_code == 200:
            domain = (r.json().get("data") or _PLAY_DOMAIN_FALLBACK).rstrip("/")
            if domain.startswith("http"):
                return domain
    except Exception:
        pass
    return _PLAY_DOMAIN_FALLBACK


def _h5_target(domain: str, path: str) -> tuple[str, dict[str, str]]:
    """Pick whether to call MovieBox directly or via the Cloudflare Worker.

    The Worker takes the upstream host + Referer in headers and forwards with
    the cookie MovieBox requires. Falls back to direct calls when no Worker
    is configured (local dev)."""
    if _PROXY_BASE:
        host = urlparse(domain).netloc
        return f"{_PROXY_BASE}{path}", {"X-Upstream-Host": host}
    return f"{domain}{path}", {}


async def _fetch_play_streams(
    domain: str,
    client: AsyncSession,
    subject_id: str,
    detail_path: str | None,
    se: int,
    ep: int,
) -> dict[str, Any]:
    referer = (
        f"{domain}/spa/videoPlayPage/movies/{detail_path or ''}"
        f"?id={subject_id}&type=/movie/detail&detailSe={se or ''}&detailEp={ep or ''}&lang=en"
    )
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "User-Agent": _BROWSER_UA,
        "X-Client-Info": _X_CLIENT_INFO,
        "X-Source": "",
    }
    params: dict[str, Any] = {"subjectId": subject_id, "se": se, "ep": ep}
    if detail_path:
        params["detailPath"] = detail_path

    target_url, proxy_headers = _h5_target(domain, _PLAY_PATH)
    if proxy_headers:
        headers.update(proxy_headers)
        headers["X-Upstream-Referer"] = referer
        if _PROXY_SECRET:
            headers["X-Auth"] = _PROXY_SECRET

    r = await client.get(
        target_url,
        headers=headers,
        params=params,
        cookies=_SESSION_COOKIES,
        timeout=30,
    )
    r.raise_for_status()
    data = (r.json() or {}).get("data") or {}
    streams = data.get("streams") or []
    codecs = sorted({(s.get("codecName") or "?") for s in streams})
    resolutions = sorted({(s.get("resolutions") or "?") for s in streams})
    logger.info(
        "[play] subject_id=%s status=%d streams=%d codecs=%s resolutions=%s",
        subject_id, r.status_code, len(streams), codecs, resolutions,
    )
    return data


async def _fetch_ext_captions(
    client: MovieBoxHttpClient, resource_id: str
) -> list[dict[str, str]]:
    """Pull MovieBox's external (SRT) caption tracks for a single resource_id.

    The H5 `/subject/download` captions field is empty for many series
    (donghua especially) — the real catalogue lives on
    `/subject-api/get-ext-captions` keyed by per-file resource_id. SRT URLs
    are CloudFront *signed URLs* (policy embedded in the querystring), so
    they're self-authenticated and our `/api/captions` SRT→VTT proxy can
    fetch them without extra headers.
    """
    if not resource_id:
        return []
    try:
        raw = await client.get_from_api(
            EXT_CAPTIONS_PATH, params={"resourceId": resource_id}
        )
    except Exception as exc:
        logger.warning(
            "[ext-captions] resource_id=%s fetch failed: %s", resource_id, exc
        )
        return []
    items = raw.get("extCaptions") or []
    return [
        {
            "lang": c.get("lanName") or c.get("lan") or "",
            "url": c.get("url") or "",
        }
        for c in items
        if c.get("url")
    ]


async def _fetch_dash_streams(
    client: MovieBoxHttpClient, subject_id: str, se: int, ep: int
) -> list[dict[str, Any]]:
    """Expand MovieBox's mobile play-info DASH manifest into one entry per
    embedded resolution.

    For series like Renegade Immortal, the 480p/720p single-episode cuts only
    exist inside this DASH (HEVC fMP4) manifest — the resource (download)
    endpoint just has the 1080p multi-episode compilation. Each returned
    entry points at the same `.mpd`; the player loads it with shaka and locks
    ABR to the chosen height.
    """
    try:
        raw = await client.get_from_api(
            PLAY_INFO_PATH,
            params={"subjectId": subject_id, "se": se, "ep": ep},
        )
    except Exception as exc:
        logger.warning(
            "[play-info] subject_id=%s se=%s ep=%s fetch failed: %s",
            subject_id, se, ep, exc,
        )
        return []
    streams = raw.get("streams") or []
    out: list[dict[str, Any]] = []
    for s in streams:
        if (s.get("format") or "").lower() != "dash":
            continue
        url = s.get("url")
        if not url:
            continue
        heights: list[int] = []
        for tok in str(s.get("resolutions") or "").split(","):
            tok = tok.strip()
            if tok.isdigit():
                heights.append(int(tok))
        if not heights:
            continue
        # File size is roughly linear in bitrate, which is roughly linear in
        # height — split the manifest's total across variants ∝ height so the
        # UI's "~MB" hint is in the right ballpark. The player only downloads
        # the chosen variant; this is a display estimate, not an exact figure.
        total = int(s.get("size") or 0)
        h_sum = sum(heights) or 1
        codec = (s.get("codecName") or "hevc").lower()
        # CloudFront signs the whole manifest tree with a Set-Cookie payload
        # that has to travel on every segment fetch. The browser can't set
        # cross-origin cookies via JS, so we hand the string to the client and
        # it routes manifest + segments through `/api/proxy?cookie=…`.
        sign_cookie = s.get("signCookie") or ""
        for h in heights:
            out.append(
                {
                    "resolution": f"{h}p",
                    "size_bytes": int(total * h / h_sum) if total else 0,
                    "url": url,
                    "codec": codec,
                    "format": "dash",
                    "target_height": h,
                    "sign_cookie": sign_cookie,
                }
            )
    logger.info(
        "[play-info] subject_id=%s se=%s ep=%s dash_variants=%d",
        subject_id, se, ep, len(out),
    )
    return out


async def _fetch_captions(
    domain: str,
    client: AsyncSession,
    subject_id: str,
    detail_path: str | None,
    se: int,
    ep: int,
) -> list[dict[str, str]]:
    referer = f"{domain}/movies/{detail_path or ''}"
    headers = {
        "Accept": "application/json",
        "Referer": referer,
        "User-Agent": _BROWSER_UA,
        "X-Client-Info": _X_CLIENT_INFO,
    }
    params = {"subjectId": subject_id, "se": se, "ep": ep}

    target_url, proxy_headers = _h5_target(domain, _DOWNLOAD_PATH)
    if proxy_headers:
        headers.update(proxy_headers)
        headers["X-Upstream-Referer"] = referer
        if _PROXY_SECRET:
            headers["X-Auth"] = _PROXY_SECRET

    try:
        r = await client.get(
            target_url,
            headers=headers,
            params=params,
            cookies=_SESSION_COOKIES,
            timeout=20,
        )
        r.raise_for_status()
        captions = ((r.json() or {}).get("data") or {}).get("captions") or []
    except Exception:
        return []
    return [
        {"lang": c.get("lanName") or c.get("lan") or "", "url": c.get("url") or ""}
        for c in captions
        if c.get("url")
    ]


async def _fetch_all_video_files(
    client: MovieBoxHttpClient,
    subject_id: str,
    *,
    max_pages: int = 20,
) -> list[VideoFileMetadata]:
    """Return EVERY file for a subject (all seasons / episodes / resolutions).

    The resource endpoint ignores se/ep filters, so the caller can only filter
    in memory — we need the full set both to satisfy that filter and to drive
    the cours/season remap. Pulling it sequentially is the dominant cost on a
    Play/Download click (~9s for a 220-episode series), so this:
      * serves a per-subject cache when warm (episodes of one series, plus the
        structure endpoint, share a single fetch);
      * fetches page 1 of each pass to learn the page count, then pulls the
        remaining pages with bounded concurrency;
      * runs the two passes (BEST archive + UNSPECIFIED low tier) together."""
    cached = _all_files_cache.get(subject_id)
    if cached is not None:
        return cached

    sem = asyncio.Semaphore(_MAX_PAGE_CONCURRENCY)

    async def fetch_page(res, page):
        async with sem:
            downloads = (
                DownloadableVideoFilesDetail(client_session=client)
                if res is None
                else DownloadableVideoFilesDetail(
                    client_session=client, resolution=res
                )
            )
            downloads.page = page
            try:
                return await downloads.get_content_model(subject_id=subject_id)
            except Exception:
                return None

    async def run_pass(res):
        first = await fetch_page(res, 1)
        if first is None:
            return []
        chunks = [first]
        pager = first.pager
        if pager.has_more:
            if pager.total_count and pager.per_page:
                total_pages = (pager.total_count + pager.per_page - 1) // pager.per_page
            else:
                total_pages = max_pages
            total_pages = min(total_pages, max_pages)
            if total_pages > 1:
                rest = await asyncio.gather(
                    *(fetch_page(res, p) for p in range(2, total_pages + 1))
                )
                chunks.extend(c for c in rest if c is not None)
        return chunks

    # Two passes pick up both the high-quality archive (default resolution)
    # and any low-quality-only episodes the BEST pass would otherwise drop.
    pass_results = await asyncio.gather(
        run_pass(None), run_pass(ResolutionType.UNSPECIFIED)
    )

    found: list[VideoFileMetadata] = []
    # Dedup on logical identity, NOT the signed URL — MovieBox re-signs on every
    # call so the URL differs across passes for the same file. BEST pass first
    # so its high-quality archive wins over the UNSPECIFIED low tier.
    seen: set[tuple[int | None, int | None, int | None, str | None]] = set()
    for chunks in pass_results:
        for chunk in chunks:
            for v in chunk.list:
                key = (
                    v.season,
                    v.episode,
                    v.resolution,
                    getattr(v, "codec_name", None),
                )
                if key in seen:
                    continue
                seen.add(key)
                found.append(v)

    _all_files_cache.set(subject_id, found)
    return found


def _remap_global_episode(
    all_files: list[VideoFileMetadata],
    requested_season: int,
    requested_episode: int,
) -> tuple[int, int] | None:
    """Translate a (season, episode) request whose tuple has no files into the
    real MovieBox (season, episode) by treating `requested_episode` as a
    linear index across MovieBox's seasons starting at `requested_season`.

    Triggered by sources (TMDB especially for anime) that lump cours/parts
    into one season while MovieBox follows the original release split.

    Example: Frieren on TMDB is S1 1..38; MovieBox is S1 1..28 + S2 1..10.
    Requested (1, 29) → walk S1 (max=28 < 29, consume), remaining=1 → walk
    S2 (max=10 ≥ 1, 1 in eps) → return (2, 1).

    Returns None when the requested index runs off the end or lands in a gap.
    """
    if requested_season < 1 or requested_episode < 1:
        return None
    by_season: dict[int, set[int]] = {}
    for f in all_files:
        if f.season is None or f.episode is None:
            continue
        by_season.setdefault(f.season, set()).add(f.episode)
    if not by_season:
        return None

    cumul = 0
    for s in sorted(s for s in by_season if s >= requested_season):
        eps = by_season[s]
        max_ep = max(eps)
        if cumul + max_ep >= requested_episode:
            local_ep = requested_episode - cumul
            return (s, local_ep) if local_ep in eps else None
        cumul += max_ep
    return None


def _is_hevc(codec: str | None, url: str | None = None) -> bool:
    c = (codec or "").lower()
    if "hevc" in c or "265" in c:
        return True
    if url:
        u = url.lower()
        # Check for common HEVC markers in URLs
        if "/h265/" in u or "/hevc/" in u:
            return True
    return False


def _prefer_hevc_per_resolution(
    variants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reduce download variants to one codec per resolution, preferring HEVC.

    For each resolution: if any HEVC variant exists, keep HEVC and drop the
    H.264 duplicate (smaller files). If a resolution has no HEVC variant, keep
    its H.264 file rather than dropping the resolution entirely — otherwise a
    title whose only HEVC encode is low-res (e.g. Frieren's 360p) loses every
    higher resolution. Result is sorted high→low like the input."""
    by_res: dict[str, dict[str, Any]] = {}
    for q in variants:
        r = q.get("resolution")
        if not r:
            continue
        is_hevc = _is_hevc(q.get("codec"), q.get("url"))
        existing = by_res.get(r)
        if existing is None:
            by_res[r] = q
            continue
        # Upgrade an H.264 pick to HEVC at the same resolution; otherwise keep
        # the first variant seen.
        if is_hevc and not _is_hevc(existing.get("codec"), existing.get("url")):
            by_res[r] = q

    return sorted(
        by_res.values(),
        key=lambda q: int(str(q["resolution"]).rstrip("p")),
        reverse=True,
    )


def _add_downloadable_streams(
    downloads: list[dict[str, Any]], play: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Backfill the download list with play-endpoint variants for any
    resolution it's missing — but only complete, single-file MP4s (not HLS
    playlists, which can't be saved as one file).

    MovieBox's H5 play endpoint sometimes hosts higher resolutions than the
    mobile resource (download) endpoint. Naruto, for example, only has 360p on
    the resource endpoint but a full 720p MP4 on the play endpoint; without
    this, its downloads cap at 360p even though 720p is right there."""
    have = {q["resolution"] for q in downloads}
    for q in play:
        if q["resolution"] in have:
            continue
        fmt = (q.get("format") or "").lower()
        url = (q.get("url") or "").split("?")[0].lower()
        if fmt == "mp4" or url.endswith(".mp4"):
            downloads.append(q)
            have.add(q["resolution"])
    return sorted(
        downloads,
        key=lambda q: int(str(q["resolution"]).rstrip("p")),
        reverse=True,
    )


def _select_best_stream(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not streams:
        return None

    def res(s: dict[str, Any]) -> int:
        try:
            return int(str(s.get("resolution") or s.get("resolutions") or 0).rstrip("p"))
        except (TypeError, ValueError):
            return 0

    return max(streams, key=res)


def _merge_for_player(
    play: list[dict[str, Any]],
    download: list[dict[str, Any]],
    dash: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Combine H5 play, mobile download, and DASH variants, deduping by
    resolution. Priority is play > download > dash, so a progressive MP4 at
    a given height wins over the DASH variant (browser-universal, no shaka
    needed). DASH fills in resolutions the MP4 sources don't have —
    typically 480p/720p single-episode cuts for series whose MP4 catalog only
    has a 1080p multi-episode compilation."""
    by_res: dict[str, dict[str, Any]] = {}
    for q in play + download + (dash or []):
        r = q.get("resolution")
        if not r or r in by_res:
            continue
        by_res[r] = q

    return sorted(
        by_res.values(),
        key=lambda q: int(str(q["resolution"]).rstrip("p")),
        reverse=True,
    )


async def _resolve(
    title: str,
    year: int | None,
    subject_type: SubjectType,
    season: int | None = None,
    episode: int | None = None,
) -> dict[str, Any] | None:
    se, ep = season or 0, episode or 0
    async with make_client() as client:
        target = await _match_query(client, title, year, subject_type)
        if target is None:
            return None
        target_subject_id, detail_path = target

        # Kick off mobile download lookup (all files) and domain discovery
        # in parallel. We fetch the full file set so we can both filter for
        # the requested (se, ep) AND drive the cours/season remap on miss.
        all_files_task = _fetch_all_video_files(client, target_subject_id)
        is_series = subject_type == SubjectType.TV_SERIES

        async with AsyncSession(impersonate=_IMPERSONATE) as web:
            domain_task = _resolve_play_domain(web)

            # Wait for both initial tasks.
            all_files, domain = await asyncio.gather(all_files_task, domain_task)

            if is_series:
                download_files = [
                    f for f in all_files
                    if f.season == se and f.episode == ep
                ]
            else:
                download_files = all_files

            # Cours/season remap: TMDB (especially for anime) sometimes
            # linearizes episodes across what MovieBox indexes as separate
            # seasons (Frieren TMDB S1=1..38 vs MovieBox S1=1..28 + S2=1..10).
            # If the requested tuple has no files but the series exists, walk
            # MovieBox's seasons as a linear index from `season`.
            eff_se, eff_ep = se, ep
            if is_series and not download_files and all_files:
                remap = _remap_global_episode(all_files, se, ep)
                if remap is not None and remap != (se, ep):
                    eff_se, eff_ep = remap
                    download_files = [
                        f for f in all_files
                        if f.season == eff_se and f.episode == eff_ep
                    ]
                    logger.info(
                        "[remap] subject_id=%s requested=(s%s,e%s) → (s%s,e%s)",
                        target_subject_id, se, ep, eff_se, eff_ep,
                    )

            # Now fetch play streams, DASH variants, and captions concurrently
            # using the (possibly remapped) effective (se, ep). Captions /
            # DASH failing must not sink the resolve, so gather with
            # return_exceptions.
            play_data, captions, dash_streams = await asyncio.gather(
                _fetch_play_streams(
                    domain, web, target_subject_id, detail_path, eff_se, eff_ep
                ),
                _fetch_captions(
                    domain, web, target_subject_id, detail_path, eff_se, eff_ep
                ),
                _fetch_dash_streams(
                    client, target_subject_id, eff_se, eff_ep
                ),
                return_exceptions=True,
            )

            if isinstance(play_data, BaseException):
                logger.warning(
                    "[play] subject_id=%s fetch failed: %s",
                    target_subject_id, play_data,
                )
                streams = []
            else:
                streams = play_data.get("streams") or []

            if isinstance(captions, BaseException):
                logger.warning(
                    "[captions] subject_id=%s fetch failed: %s",
                    target_subject_id, captions,
                )
                captions = []

            if isinstance(dash_streams, BaseException):
                logger.warning(
                    "[play-info] subject_id=%s fetch failed: %s",
                    target_subject_id, dash_streams,
                )
                dash_streams = []

            # Merge in MovieBox's external SRT captions (the H5 /subject/download
            # response is sparse; the mobile ext-captions endpoint is where the
            # English/etc. tracks actually live for series). Keyed by the
            # episode's resource_id, so pick any file we already fetched for
            # (eff_se, eff_ep).
            resource_id_for_caps = next(
                (f.resource_id for f in download_files if f.resource_id),
                "",
            )
            ext_caps = await _fetch_ext_captions(client, resource_id_for_caps)
            if ext_caps:
                seen_urls = {c.get("url") for c in captions}
                captions = list(captions) + [
                    c for c in ext_caps if c.get("url") not in seen_urls
                ]

    qualities: list[dict[str, Any]] = []
    for s in streams:
        url = s.get("url")
        resolution = s.get("resolutions")
        if not url or not resolution:
            continue
        qualities.append(
            {
                "resolution": f"{resolution}p",
                "size_bytes": s.get("size") or 0,
                "url": url,
                "codec": s.get("codecName") or "",
                "format": s.get("format") or "",
            }
        )
    qualities.sort(key=lambda q: int(str(q["resolution"]).rstrip("p")), reverse=True)

    download_qualities: list[dict[str, Any]] = []
    for v in download_files:
        url = str(v.resource_link) if v.resource_link else None
        if not url or not v.resolution:
            continue
        download_qualities.append(
            {
                "resolution": f"{v.resolution}p",
                "size_bytes": int(v.size or 0),
                "url": url,
                "codec": getattr(v, "codec_name", "") or "",
                "format": "",
            }
        )
    download_qualities.sort(
        key=lambda q: int(str(q["resolution"]).rstrip("p")), reverse=True
    )

    logger.info(
        "[resolve] subject_id=%s play_qualities=%d download_qualities=%d "
        "play_codecs=%s download_codecs=%s",
        target_subject_id,
        len(qualities),
        len(download_qualities),
        sorted({q.get("codec") or "?" for q in qualities}),
        sorted({q.get("codec") or "?" for q in download_qualities}),
    )

    # Coming Soon: nothing to play AND nothing to download.
    if not qualities and not download_qualities:
        return None

    # Snapshot the play (H5) variants before the merge mutates `qualities` —
    # some serve resolutions the mobile download endpoint never returns.
    play_only = qualities

    # Merge play + download + DASH variants for the streaming pool. DASH
    # only fills resolutions the MP4 sources don't cover (see
    # `_merge_for_player`), and the download list stays MP4-only — DASH
    # manifests can't be saved as a single file.
    qualities = _merge_for_player(qualities, download_qualities, dash_streams)
    # Downloads prefer HEVC (smaller files), but fall back to H.264 per
    # resolution: if a resolution only exists as H.264, keep it rather than
    # drop it. Otherwise titles whose high-res ladder is H.264-only (e.g.
    # Frieren: 1080p/h264 + 360p/hevc) would collapse to just the 360p HEVC.
    download_qualities = _prefer_hevc_per_resolution(download_qualities)
    # Backfill resolutions the download endpoint lacks with downloadable
    # (single-file MP4) play streams (e.g. Naruto: 360p download + 720p play).
    download_qualities = _add_downloadable_streams(download_qualities, play_only)
    logger.info(
        "[resolve] subject_id=%s post_merge_qualities=%d post_merge_codecs=%s "
        "hevc_downloads=%d",
        target_subject_id,
        len(qualities),
        sorted({q.get("codec") or "?" for q in qualities}),
        len(download_qualities),
    )

    # If MovieBox returns no variants at all, try fzmovies for a 480p h264 mp4.
    # Movies only — fzmovies-api doesn't model series.
    stream_source = "moviebox"
    if not qualities and se == 0 and ep == 0 and title:
        fzm = await fzmovies.resolve_h264(title, year)
        if fzm:
            qualities = [fzm]
            stream_source = "fzmovies"

    chosen = _select_best_stream(qualities)
    final_stream_url = chosen["url"] if chosen else None
    final_codec = (chosen.get("codec") if chosen else "") or ""
    final_format = (chosen.get("format") if chosen else "") or ""

    # Referer is MovieBox-CDN-specific. fzmovies' final URL doesn't enforce
    # one (we tested), so leave it empty when streaming from fzmovies.
    play_referer = "" if stream_source == "fzmovies" else domain.rstrip("/") + "/"

    return {
        "stream_url": final_stream_url,
        "stream_codec": final_codec,
        "stream_format": final_format,
        # CDN does Referer-allowlisting against MovieBox's current play domain.
        # The browser can't spoof Referer, so the proxy needs this to fetch bytes.
        "play_referer": play_referer,
        "qualities": qualities,
        "download_qualities": download_qualities,
        "captions": captions,
        "source": stream_source,
    }


@router.get("/stream/movie")
async def stream_movie(
    title: str = Query(...),
    year: int | None = Query(default=None),
    tmdb_id: int | None = Query(default=None),
    anilist_id: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id or anilist_id, title, year, None, None)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    resolved = await _resolve_with_alt_titles(
        title, year, SubjectType.MOVIES,
        tmdb_id=tmdb_id, anilist_id=anilist_id,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail={"error": "unavailable"})

    _cache.set(key, resolved)
    return resolved


@router.get("/stream/series")
async def stream_series(
    title: str = Query(...),
    season: int = Query(...),
    episode: int = Query(...),
    year: int | None = Query(default=None),
    tmdb_id: int | None = Query(default=None),
    anilist_id: int | None = Query(default=None),
) -> dict[str, Any]:
    key = _cache_key(tmdb_id or anilist_id, title, year, season, episode)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    resolved = await _resolve_with_alt_titles(
        title, year, SubjectType.TV_SERIES,
        tmdb_id=tmdb_id, anilist_id=anilist_id,
        season=season, episode=episode,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail={"error": "unavailable"})

    _cache.set(key, resolved)
    return resolved


@router.get("/series/structure")
async def series_structure(
    title: str = Query(...),
    year: int | None = Query(default=None),
    tmdb_id: int | None = Query(default=None),
    anilist_id: int | None = Query(default=None),
) -> dict[str, Any]:
    """Authoritative season/episode structure for a series, in MovieBox's own
    numbering, with source (TMDB) episode names overlaid where they line up.

    The frontend drives its season/episode pickers from this so the (se, ep)
    it sends to `/stream/series` is already in MovieBox's coordinate system —
    no cross-source remap needed, and it works for every series, not just the
    ones the heuristic happened to cover."""
    key = f"struct:{_cache_key(tmdb_id or anilist_id, title, year, None, None)}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    async def _moviebox_files() -> tuple[str, list[VideoFileMetadata]] | None:
        async with make_client() as client:
            matched = await _match_target_subject(
                client, title, year, SubjectType.TV_SERIES,
                tmdb_id=tmdb_id, anilist_id=anilist_id,
            )
            if matched is None:
                return None
            sid, _ = matched
            return sid, await _fetch_all_video_files(client, sid)

    # The MovieBox lookup and the TMDB episode fetch are independent (TMDB only
    # needs tmdb_id) — run them concurrently. AniList per-episode titles are
    # unreliable, so anime gets correct numbering with "Episode N" names.
    files_result, ep_meta = await asyncio.gather(
        _moviebox_files(),
        _fetch_tmdb_episode_meta(tmdb_id) if tmdb_id else _empty_meta(),
    )
    if files_result is None:
        raise HTTPException(status_code=404, detail={"error": "unavailable"})
    target_subject_id, all_files = files_result

    season_map: dict[int, list[int]] = {}
    for f in all_files:
        if f.season is None or f.episode is None:
            continue
        eps = season_map.setdefault(f.season, [])
        if f.episode not in eps:
            eps.append(f.episode)
    if not season_map:
        raise HTTPException(status_code=404, detail={"error": "no_episodes"})

    result = {
        "subject_id": target_subject_id,
        "seasons": _build_structure(season_map, ep_meta),
    }
    _cache.set(key, result)
    return result
