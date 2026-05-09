/**
 * Cloudflare Worker — MovieBox H5 API proxy.
 *
 * MovieBox IP-blocks our Render backend on the H5 play domain (netfilm.world).
 * This Worker runs on Cloudflare's IPs (not blocked) and forwards H5 requests
 * with the Referer + uuid cookie that MovieBox requires for non-empty stream
 * responses — neither of which the browser is allowed to set cross-origin.
 *
 * Backend → Worker → MovieBox H5 API → Worker → Backend.
 *
 * Routing: anything under /wefeed-h5api-bff/ is forwarded.
 * Upstream host: read from `X-Upstream-Host` header (backend does domain
 * discovery and tells us where to send), defaults to netfilm.world.
 * Upstream Referer: read from `X-Upstream-Referer` header.
 *
 * Auth: optional shared secret in `X-Auth` header (set via PROXY_SECRET env).
 * Required in production so this isn't a public open proxy.
 */

const DEFAULT_UPSTREAM_HOST = 'netfilm.world';
const UUID_COOKIE = 'uuid=d8c3539e-2e46-4000-af20-7046a856e30a';
const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith('/wefeed-h5api-bff/')) {
      return new Response('not a proxied path', { status: 404 });
    }

    if (env.PROXY_SECRET && request.headers.get('X-Auth') !== env.PROXY_SECRET) {
      return new Response('unauthorized', { status: 401 });
    }

    const upstreamHost = request.headers.get('X-Upstream-Host') || DEFAULT_UPSTREAM_HOST;
    const upstreamReferer = request.headers.get('X-Upstream-Referer') || `https://${upstreamHost}/`;
    const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;

    const headers = {
      'Accept': request.headers.get('Accept') || 'application/json',
      'Accept-Language': 'en-US,en;q=0.9',
      'User-Agent': BROWSER_UA,
      'X-Client-Info': '{"timezone":"Africa/Nairobi"}',
      'X-Source': '',
      'Referer': upstreamReferer,
      'Cookie': UUID_COOKIE,
    };

    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
    });

    const respHeaders = new Headers(upstream.headers);
    // CF auto-decodes; the original encoding header would be wrong for the body we pass through.
    respHeaders.delete('content-encoding');
    respHeaders.delete('content-length');

    return new Response(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  },
};
