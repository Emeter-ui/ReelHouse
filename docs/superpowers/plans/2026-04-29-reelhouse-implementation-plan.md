# Reelhouse — Implementation Plan

**Status:** Frontend complete (F0–F5) ✓ · Backend (B0–B4) blocked on `uv` install
**Date:** 2026-04-29
**Spec:** `docs/superpowers/specs/2026-04-29-reelhouse-streaming-site-design.md`

Phased build. Each phase has bite-sized steps and a verification gate. Frontend phases (F*) come first because Python is not yet installed. Backend phases (B*) start once `uv` + Python 3.14 are available.

## F0 — Repo bootstrap
- `git init`, set default branch to `main`.
- Root `.gitignore` (Node + Python + `.env` + IDE).
- Move legacy Netlify deploy artifacts (`_nuxt/`, `_headers`, `_redirects`, `netlify.toml`, `favicon.ico`, `robots.txt`) into `_legacy/` so they remain available as a visual reference but are not part of the new build.
- Root `README.md` skeleton.
- Initial commit.

## F1 — Frontend scaffold
- Create `frontend/` with manual Nuxt 3 layout (no interactive `nuxi init`).
- `package.json` — Nuxt 3, `@nuxtjs/tailwindcss`, `vidstack`, `@vueuse/core`.
- `nuxt.config.ts` — Tailwind module, runtimeConfig with `apiBase`, css entry.
- `tsconfig.json`, `tailwind.config.ts`, `app.vue`.
- `assets/css/main.css` — dark theme tokens sampled from the legacy `entry.mbtcuxoj.css`.
- `frontend/.env.example` with `NUXT_PUBLIC_API_BASE=http://localhost:8000`.

**Verify:** `npm install` succeeds; `npm run dev` boots without error.

## F2 — Composables
- `composables/useTmdb.ts` — thin wrapper over `useFetch` against `${apiBase}/api/tmdb/...`.
- `composables/useStream.ts` — wraps stream-resolve endpoints.
- `composables/useMyList.ts` — localStorage `reelhouse:v1:myList`, debounced writes, cross-tab sync, FIFO cap 100.
- `composables/useContinueWatching.ts` — same shape, key `reelhouse:v1:continueWatching`.

## F3 — Components
- `components/MovieCard.vue` — poster, title, rating, hover overlay.
- `components/MovieRow.vue` — horizontal scroller with tab switching (Popular/Top Rated/Upcoming).
- `components/Hero.vue` — large featured banner with backdrop, ▶ Play / + My List CTAs.
- `components/FilterSidebar.vue` — Year, Genre, Sort.
- `components/CollectionCard.vue`.
- `components/Player.vue` — Vidstack wrapper with two-layer playback (HEAD probe → fall back to `/api/proxy?url=...`); `timeupdate` → `useContinueWatching` (throttled 5s; add at 30s; remove at 95%).
- `components/CategoryFilter.vue` — tab/filter pill row.
- `components/AppHeader.vue` — logo, nav, search.

## F4 — Pages
File-based routes per spec table:
- `pages/index.vue` — Hero + rows (Trends, Movies tabs, Series tabs, Now Playing, Continue Watching).
- `pages/movies.vue` — sidebar + grid + pagination.
- `pages/series.vue` — same shape.
- `pages/collection/index.vue`, `pages/collection/[id].vue`.
- `pages/movie/[id].vue`, `pages/series/[id].vue` (series with seasons/episodes).
- `pages/search.vue` — `?q=`.
- `pages/my-list.vue` — list + JSON export/import.
- `pages/watch/movie/[id].vue`, `pages/watch/series/[id]/s/[season]/e/[episode].vue`.

**Verify:** every route resolves (404s should not appear for the listed paths). Visual diff against `_legacy/` screenshots is "close enough" but we don't reproduce the broken UX.

## F5 — Frontend smoke
- `npm install`, `npm run dev`.
- Open each route in the browser, confirm shells render even without backend (loading or empty states; no uncaught errors in console).
- Update `README.md` with run instructions and "real data needs backend (Phase B*)".
- Commit.

---
## B0 — Backend prerequisites *(blocked until `uv` is installed)*
- User installs `uv`. We then run `uv python install` which honours `.python-version`.

## B1 — Backend scaffold
- `backend/pyproject.toml` — FastAPI, uvicorn, httpx, rapidfuzz, python-dotenv, plus `moviebox-api` as a path dependency to `../moviebox-api-main`.
- `backend/app/main.py` — FastAPI app, CORS for `http://localhost:3000`, mount routers.
- `backend/app/cache.py` — in-memory TTL cache.
- `backend/app/routes/tmdb.py` — catch-all proxy with 1h LRU.
- `backend/app/routes/healthz.py`.
- `backend/.env` (gitignored) with the TMDB key.
- `backend/.env.example` (committed).

**Verify:** `uvicorn app.main:app --reload --port 8000` boots; `curl /api/healthz` ok; `curl /api/tmdb/movie/popular` returns TMDB JSON.

## B2 — Stream resolution
- `backend/app/matching.py` — title+year → moviebox match (rapidfuzz, threshold 85, year ±1).
- `backend/app/routes/stream.py` — `/api/stream/movie`, `/api/stream/series`. 30-min TTL cache.

**Verify:** end-to-end resolve for a known title returns `{stream_url, qualities, captions, source}`.

## B3 — Byte proxy
- `backend/app/routes/proxy.py` — async `httpx` byte streamer with appropriate UA and Referer; passes through `Range`.

**Verify:** seek + scrub work in the player when forced through the proxy.

## B4 — End-to-end smoke
- Start both services. Walk: home → search → detail → watch → continue watching → my list.
- Document run instructions in root `README.md`.
- Tag `v0.1.0`.

## Open follow-ups (not in this plan)
- Production hosting (Netlify for frontend, Fly/Render for backend).
- Persistent cache (Redis) once we know hit-rates.
- Caption styling polish.
