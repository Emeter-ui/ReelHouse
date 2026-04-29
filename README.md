# Reelhouse

Personal streaming site. Nuxt 3 frontend + FastAPI backend; TMDB metadata, moviebox-api stream resolution. localStorage-only persistence.

See `docs/superpowers/specs/2026-04-29-reelhouse-streaming-site-design.md` for the design spec and `docs/superpowers/plans/2026-04-29-reelhouse-implementation-plan.md` for the build plan.

## Run (dev)

### Frontend
```bash
cd frontend
cp .env.example .env        # then edit if backend isn't on :8000
npm install
npm run dev                 # http://localhost:3000
```

### Backend (requires Python 3.12+ via uv)
```bash
# one-time: install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd backend
cp .env.example .env        # add your TMDB_API_KEY
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## Layout

```
frontend/          Nuxt 3 app
backend/           FastAPI app (path-depends on ../moviebox-api-main)
moviebox-api-main/ vendored Python library
_legacy/           original Netlify deploy bundles, kept as a visual reference
docs/              spec + plan
```

## Status

- Frontend: built, runs against backend at `NUXT_PUBLIC_API_BASE`.
- Backend: scaffolded — needs Python 3.12+ (`uv` recommended) before it can run.
- Personal use only. Do not publish.
