# reelhouse-consumet

Thin Express wrapper around `@consumet/extensions`, deployed to Fly.io as the
anime/donghua backend for `/api/donghua/*` in `reelhouse-backend`.

## Why not the official Consumet API?

`github.com/consumet/api.consumet.org` was taken down by GitHub in 2026
(HTTP 451 — DMCA), so we can't `git clone` it during the Docker build. The
underlying `@consumet/extensions` scraper library is still on npm, so we
ship our own ~80-line wrapper (`server.js`) that mirrors the original API
shape well enough for our backend.

## Routes

Same shape as the original API:

- `GET /anime/:provider/:query` — search (page via `?page=`)
- `GET /anime/:provider/info?id=…` — episode list + metadata
- `GET /anime/:provider/watch/:episodeId?server=…` — HLS `.m3u8` sources

Providers: `hianime` (alias `zoro`), `animekai`. Consumet 1.8 renamed Zoro
to Hianime; the alias keeps the backend's `?provider=zoro` string working.

## Deploy

```bash
cd consumet-server
fly launch --no-deploy    # first time only — adopts fly.toml as-is
fly deploy
```

Backend reads `CONSUMET_BASE_URL` (default
`http://reelhouse-consumet.internal:3000`) so the two Fly apps talk over
Fly's private 6PN network.

## Upgrading @consumet/extensions

Bump the pinned version in `package.json` and redeploy. When a provider
class rename happens (as Zoro→Hianime did), add an alias in `server.js`'s
`PROVIDERS` map so old backend calls keep working.
