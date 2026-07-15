# Thin wrapper over the upstream FlareSolverr image. Kept in its own
# directory so we can pin a specific tag and add Fly-specific tuning.
FROM ghcr.io/flaresolverr/flaresolverr:latest

# FlareSolverr honours LOG_LEVEL, PORT, HOST, LOG_HTML, CAPTCHA_SOLVER,
# TZ, HEADLESS. Defaults here — override via `fly secrets set` if needed.
ENV LOG_LEVEL=info
ENV TZ=UTC
ENV HEADLESS=true
# Fly's 6PN private network is IPv6-only. FlareSolverr defaults to
# 0.0.0.0 (IPv4 only) which is unreachable from sibling apps — bind
# to :: so the socket accepts both v4 and v6 traffic.
ENV HOST=::

EXPOSE 8191
