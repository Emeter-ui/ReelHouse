# reelhouse-flaresolverr

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) on Fly.io.

Cloudflare shields hianime/aniwatch/megacloud with JS + TLS-fingerprint
challenges that plain HTTP clients (axios, node-fetch, curl) can't pass.
FlareSolverr runs headless Chromium, solves the challenge, and hands back
the cookies + HTML.

## Deploy

```bash
cd flaresolverr-server
fly launch --no-deploy    # first time — adopts fly.toml
fly deploy
```

## Access

**Private only.** No public HTTP. Reachable from other Fly apps in the
same org at `http://reelhouse-flaresolverr.internal:8191`.

The `reelhouse-consumet` server reads `FLARESOLVERR_URL` (default
`http://reelhouse-flaresolverr.internal:8191/v1`) and POSTs
`{ "cmd": "request.get", "url": "…", "maxTimeout": 60000 }` to it.

## Ops notes

- Chromium needs ~800MB steady-state; VM sized at 1GB.
- Sessions can be reused via `session` param to reduce cold-start cost.
- Cloudflare updates sometimes break FlareSolverr — bump the image tag
  by editing the `FROM` line in `Dockerfile` and redeploying.
