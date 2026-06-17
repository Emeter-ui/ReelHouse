/**
 * Cloudflare Worker — MovieBox API proxy.
 *
 * MovieBox IP-blocks our Fly backend on two surfaces:
 *   - the H5 play domain (netfilm.world / h5.aoneroom.com), used by /subject/play
 *   - the mobile-bff API (api6.aoneroom.com), used by /resource, /play-info,
 *     /season-info — i.e. downloads, DASH variants, and the structure endpoint
 *
 * This Worker runs on Cloudflare's IPs (not blocked) and forwards both kinds
 * of request. Backend → Worker → MovieBox → Worker → Backend.
 *
 * Routing
 *   /wefeed-h5api-bff/*    → H5 play domain. Worker injects Referer + uuid cookie
 *                            (browser can't set them cross-origin) and pretends
 *                            to be Chrome.
 *   /wefeed-mobile-bff/*   → mobile-bff API host. Worker forwards the signed
 *                            request as-is. The signature is over path+query
 *                            only, so swapping the host doesn't invalidate it.
 *                            The `x-user` response header (bearer-token refresh)
 *                            is passed back so the client picks up new tokens.
 *
 * Upstream host
 *   H5: `X-Upstream-Host` header (backend does domain discovery and tells us).
 *       Default `netfilm.world`.
 *   mobile-bff: `X-Upstream-Host` header. Default `api6.aoneroom.com`.
 *
 * Auth: optional shared secret in `X-Auth` header (set via PROXY_SECRET env).
 * Required in production so this isn't a public open proxy.
 */

const DEFAULT_H5_HOST = 'netfilm.world';
const DEFAULT_MOBILE_HOST = 'api6.aoneroom.com';
const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// Fresh UUID per request so a single hardcoded cookie can't be blacklisted.
function freshUuid() {
  return crypto.randomUUID();
}

// Headers the mobile-bff signature depends on (or that the API checks for shape).
// We pass these through verbatim from the backend so the signed request stays valid.
const MOBILE_PASSTHROUGH_HEADERS = [
  'authorization',
  'x-client-token',
  'x-tr-signature',
  'x-client-info',
  'x-client-status',
  'x-play-mode',
  'user-agent',
  'accept',
  'content-type',
];

// Response headers worth forwarding from the upstream back to the backend.
// `x-user` carries the runtime token refresh, so it's critical to preserve.
const MOBILE_RESPONSE_HEADERS = ['content-type', 'x-user'];

function corsAllowAll(headers) {
  headers.set('Access-Control-Allow-Origin', '*');
  return headers;
}

async function handleH5(request, env, url) {
  const upstreamHost = request.headers.get('X-Upstream-Host') || DEFAULT_H5_HOST;
  const upstreamReferer = request.headers.get('X-Upstream-Referer') || `https://${upstreamHost}/`;
  const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;

  const headers = {
    'Accept': request.headers.get('Accept') || 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'User-Agent': BROWSER_UA,
    'X-Client-Info': '{"timezone":"Africa/Nairobi"}',
    'X-Source': '',
    'Referer': upstreamReferer,
    'Cookie': `uuid=${freshUuid()}`,
    // Mimic what a real browser would send when navigating from netfilm.world.
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
  };

  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
  });

  if (upstream.status >= 400) {
    const bodyText = await upstream.clone().text().catch(() => '<unreadable>');
    console.log(`H5 UPSTREAM ${upstream.status} body=${bodyText.slice(0, 500)}`);
  }

  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete('content-encoding');
  respHeaders.delete('content-length');
  return new Response(upstream.body, { status: upstream.status, headers: respHeaders });
}

async function handleMobile(request, env, url) {
  const upstreamHost = request.headers.get('X-Upstream-Host') || DEFAULT_MOBILE_HOST;
  const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;

  // Forward the SIGNED headers verbatim. The signature is over path+query (not
  // host), so as long as we leave URL+headers untouched the upstream's
  // signature check passes.
  const headers = {};
  for (const name of MOBILE_PASSTHROUGH_HEADERS) {
    const v = request.headers.get(name);
    if (v) headers[name] = v;
  }
  if (!headers['user-agent']) headers['user-agent'] = BROWSER_UA;

  let body;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    body = await request.arrayBuffer();
  }

  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
  });

  if (upstream.status >= 400) {
    const bodyText = await upstream.clone().text().catch(() => '<unreadable>');
    console.log(`MOBILE UPSTREAM ${upstream.status} body=${bodyText.slice(0, 500)}`);
  }

  // Build a clean response — we only forward headers MobileBoxHttpClient cares
  // about (content-type for body parsing, x-user for token refresh).
  const respHeaders = new Headers();
  for (const name of MOBILE_RESPONSE_HEADERS) {
    const v = upstream.headers.get(name);
    if (v) respHeaders.set(name, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: corsAllowAll(respHeaders) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (env.PROXY_SECRET && request.headers.get('X-Auth') !== env.PROXY_SECRET) {
      return new Response('unauthorized', { status: 401 });
    }

    if (url.pathname.startsWith('/wefeed-h5api-bff/')) {
      return handleH5(request, env, url);
    }
    if (url.pathname.startsWith('/wefeed-mobile-bff/')) {
      return handleMobile(request, env, url);
    }
    return new Response('not a proxied path', { status: 404 });
  },
};
