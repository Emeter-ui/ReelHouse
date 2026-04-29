# Reelhouse — Streaming Site Rebuild

**Status:** Approved (brainstorming)
**Date:** 2026-04-29
**Author:** Dave + Claude

## Context

The user previously deployed a Nuxt 3 streaming site ("JFK Streaming") to Netlify at `dulcet-dodol-5a20da.netlify.app`. Source code was lost with their GitHub account. Only the deployed minified bundles remain (in `_nuxt/`) plus a vendored Python library (`moviebox-api-main/`) that wraps `moviebox.ph` for search and stream-URL resolution.

Inspecting the deployed site shows it was an unfinished mockup: cards repeated 3× per row, all detail links pointed at `/movie/undefined`, posters were Unsplash placeholders, filter values were hardcoded labels. So this project is a **faithful rebuild of the design** with a real working backend behind it — not a recovery of the original code.

## Goals

- A working personal streaming site that visually matches the original mockup.
- Browse, search, view detail, and watch movies and TV series in the browser.
- Save items to "My List" and resume from "Continue Watching" — both browser-local.
- Two cleanly separated services: Nuxt 3 frontend + small FastAPI backend.
- Local-first development; hosting decisions deferred until streams are validated.

## Non-Goals

- **Anime** — explicitly out of scope; no `/anime` route.
- **User accounts / multi-device sync** — localStorage only, no auth, no DB.
- **Country / Actor / Director filters** — original mockup had hardcoded labels; cut to keep build tight. Year + Genre + Sort only.
- **Public deployment / sharing** — personal use; rate-limit and copyright concerns make wide publication a bad idea.
- **Original mockup's exact copy of broken UX** — `/movie/undefined` links, repeating card grids, Unsplash placeholders are not reproduced.

## Architecture

Two services, run separately:

```
Browser (Nuxt 3 frontend, Netlify in prod)
   │
   ▼
  /api/*   ────────►  FastAPI backend (Python, local for now)
                          │
                          ├── TMDB API     (titles, posters, ratings, cast, lists)
                          └── moviebox-api (resolve stream/download URLs on play)
```

**Frontend** owns all UI and routing. Talks only to the FastAPI backend — never directly to TMDB or moviebox. Keeps the TMDB key server-side and hides CORS issues behind one origin.

**Backend** is small. Three responsibilities:
1. Proxy TMDB calls (with caching) so the key never reaches the browser.
2. Resolve a stream URL via `moviebox-api` when the user hits Play.
3. Byte-proxy the actual video stream when the source CDN blocks CORS.

**No database.** My List + Continue Watching live in browser `localStorage`.

## Pages & Routes (Frontend)

| Route | Page | Notes |
|---|---|---|
| `/` | Home | Hero, Trends, Movies tabs (Popular/Top Rated/Upcoming), Series tabs (Popular/Top Rated/On TV), Now Playing, Continue Watching |
| `/movies` | Movies browse | Filter sidebar (Year, Genre, Sort) + paginated grid |
| `/series` | Series browse | Same shape as movies |
| `/collection` | Collections | TMDB collections (Marvel, DC, Star Wars, etc.) — featured hero + grid |
| `/collection/[id]` | Single collection | All movies in a TMDB collection |
| `/movie/[id]` | Movie detail | Poster, overview, cast, similar, ▶ Play, + My List |
| `/series/[id]` | Series detail | Seasons + episodes list |
| `/watch/movie/[id]` | Player | Video player + back/title overlay |
| `/watch/series/[id]/s/[season]/e/[episode]` | Episode player | Same, with episode metadata |
| `/search?q=...` | Search results | TMDB multi-search |
| `/my-list` | My List | localStorage-backed; export/import JSON |

## Backend API

| Endpoint | Purpose |
|---|---|
| `GET /api/tmdb/{...path}` | Catch-all TMDB proxy. Backend appends API key. LRU + 1h TTL cache. |
| `GET /api/stream/movie?tmdb_id=&title=&year=` | Resolve a movie's stream URL via moviebox-api. |
| `GET /api/stream/series?tmdb_id=&title=&season=&episode=` | Resolve an episode's stream URL. |
| `GET /api/proxy?url=...` | Byte-stream a remote video through the backend (CORS / Referer fallback). |
| `GET /api/healthz` | Liveness check for future hosting. |

Stream-resolve responses:
```json
{
  "stream_url": "https://...",
  "qualities": ["1080p","720p","480p"],
  "captions": [{"lang":"English","url":"https://..."}],
  "source": "moviebox"
}
```

`404 {"error":"unavailable"}` if no match found.

## Data Flow

**Browse / metadata** (no moviebox involved):
1. Frontend → `GET /api/tmdb/movie/popular`
2. Backend forwards to TMDB with key, caches response.
3. Frontend renders cards using TMDB poster URLs directly (TMDB image CDN is browser-friendly).

**Play**:
1. User clicks ▶ on `/movie/[id]`.
2. Navigate to `/watch/movie/[tmdb_id]`.
3. Watch page → `GET /api/stream/movie?tmdb_id=123&title=Avatar&year=2009`.
4. Backend uses `moviebox-api` to search + resolve, returns stream URL + qualities + captions.
5. If no match → `404`. Frontend shows "Source unavailable — try another title".

**Series episode**: same pattern but `?season=1&episode=1`.

## Title-to-Source Matching

`moviebox-api` searches by title string; TMDB has stable numeric IDs. Bridging:

- Exact title + year match wins.
- Else fuzzy match via `rapidfuzz` on title with year ±1 tolerance, threshold 85.
- Else first result if confidence ≥ 70.
- Else 404.

## Caching

- TMDB responses: in-memory LRU, 1h TTL.
- Stream URL resolutions: in-memory, 30 min TTL, keyed by `(tmdb_id, season?, episode?)`.
- Cache is process-local (lost on restart). Acceptable for dev and single-instance deploy.

## Streaming & Player

**Two-layer playback strategy** (we don't yet know moviebox CDN's CORS posture):

1. **Try direct first.** Watch page does a `HEAD` probe to the stream URL. If 200 with permissive CORS → drop into `<video>`.
2. **Fall back to backend proxy.** On probe failure, swap source to `/api/proxy?url=<encoded>`. Backend opens an `httpx` stream with appropriate User-Agent and Referer, pipes bytes to client.

**Player: Vidstack** — modern Vue/web-component player, HLS support built in, keyboard shortcuts, captions, fullscreen, PiP. Plyr considered but lacks native HLS.

**Captions**: backend resolves caption URLs from moviebox-api (English default). Captions also flow through `/api/proxy` to dodge CORS.

**Continue Watching trigger**:
- Player `timeupdate` events; saves throttled to every 5s.
- Add to Continue Watching after 30s watched.
- Auto-remove when ≥95% complete.
- Resume from saved position on next play.

## Persistence (localStorage)

Two namespaced, schema-versioned keys:

```js
// localStorage["reelhouse:v1:myList"]
[
  { "id": 76600, "type": "movie", "title": "Avatar: The Way of Water",
    "poster": "/abc.jpg", "year": 2022, "addedAt": 1730000000000 }
]

// localStorage["reelhouse:v1:continueWatching"]
[
  { "id": 1399, "type": "series", "title": "Game of Thrones",
    "poster": "/xyz.jpg", "season": 1, "episode": 3,
    "position": 842, "duration": 3300, "updatedAt": 1730000000000 }
]
```

- Composables `useMyList()` and `useContinueWatching()` wrap reads/writes; debounce saves at 250ms.
- Capped at 100 entries each, FIFO eviction.
- Cross-tab sync via the `storage` event.
- Export / import (JSON file) buttons on `/my-list`.

## Project Structure

```
reelhouse/
├── frontend/                Nuxt 3 app
│   ├── pages/               file-based routes (see table above)
│   ├── components/          MovieCard, MovieRow, Hero, FilterSidebar, Player, …
│   ├── composables/         useTmdb, useStream, useMyList, useContinueWatching
│   ├── assets/css/          Tailwind config, dark theme tokens
│   └── nuxt.config.ts
├── backend/                 FastAPI
│   ├── app/
│   │   ├── main.py          app + CORS for frontend origin
│   │   ├── routes/
│   │   │   ├── tmdb.py      catch-all proxy + LRU cache
│   │   │   ├── stream.py    /api/stream/movie, /api/stream/series
│   │   │   └── proxy.py     /api/proxy byte-streamer
│   │   ├── matching.py      title+year → moviebox match (rapidfuzz)
│   │   └── cache.py         in-memory TTL cache
│   ├── pyproject.toml       depends on moviebox-api (path = "../moviebox-api-main")
│   └── .env.example         TMDB_API_KEY=, FRONTEND_ORIGIN=
├── moviebox-api-main/       already vendored
├── docs/superpowers/specs/  this doc + future plans
└── README.md                run instructions
```

**Styling**: Tailwind CSS, dark-only theme. Colour palette and rough proportions sampled from the deployed site's `_nuxt/entry.mbtcuxoj.css`.

**Local dev**:
- `cd backend && uvicorn app.main:app --reload --port 8000`
- `cd frontend && npm run dev` → http://localhost:3000
- Frontend `runtimeConfig.public.apiBase = 'http://localhost:8000'`

## Open Risks

1. **Stream playability** — unknown until first end-to-end test. Proxy fallback designed in.
2. **moviebox.ph rate limiting / blocking** — third-party site, can block IPs or change shape. Mitigation: aggressive caching, graceful "Source unavailable".
3. **TMDB ⇄ moviebox match miss rate** — catalog gaps inevitable. Surfaced, not silenced.
4. **TMDB image CDN hot-link blocking** — rare but possible from new domains. Backend can proxy images as last resort.
5. **Bandwidth on proxy fallback** — every minute of proxied playback eats backend bandwidth. Personal use only.
6. **Legality** — same disclaimer as upstream `moviebox-api`: personal use, don't publicize.

## Out of Scope (Explicit)

- `/anime` route
- User accounts, login, multi-device sync
- Country / Actor / Director filters
- Comments, reviews, ratings submission
- Subtitle search beyond what moviebox-api returns
- Recommendations beyond TMDB's "similar" endpoint
- PWA / offline / downloads

## Decisions Locked

| # | Question | Answer |
|---|---|---|
| 1 | Architecture path | A — TMDB metadata + moviebox-api streams (hybrid) |
| 2 | Persistence | A — localStorage only, no accounts |
| 3 | Tech stack | A — Nuxt 3 frontend + FastAPI backend |
| 4 | Hosting | A — local-first dev; defer hosting until streams work |
| 5 | TMDB key | Provided; goes in `backend/.env` (gitignored) |
| 6 | Branding | "Reelhouse" |
