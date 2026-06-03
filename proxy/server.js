// Fly.io MovieBox H5 proxy — same logic as worker/moviebox-proxy.js but
// running on Fly so we can pin egress to a region MovieBox allows (the H5
// surface returns "invalid region" 403 from US-based hosts).
//
// Routes:
//   /wefeed-h5api-bff/*   — JSON H5 API (MovieBox blocks US/Africa egress)
//   /cdn?url=...&referer= — byte streaming for hakunaymatata.com CDNs
//                           (datacenter IPs get 403 even with right Referer)

import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const PORT = process.env.PORT || 8080;
const PROXY_SECRET = process.env.PROXY_SECRET || '';
const DEFAULT_UPSTREAM_HOST = 'netfilm.world';
const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// /cdn proxies bytes from any *.hakunaymatata.com host. The CDN allowlists
// Referer against MovieBox's H5 domain AND blocks datacenter egress, so the
// caller has to provide the Referer and we have to be the one fetching from
// a Fly region the CDN trusts.
const CDN_ALLOWED_HOST_SUFFIX = '.hakunaymatata.com';
// Headers from upstream we want to surface to the caller. Anything else
// (set-cookie, server, x-oss-*, etc.) is dropped.
const CDN_PASSTHROUGH_HEADERS = new Set([
  'content-type',
  'content-length',
  'content-range',
  'accept-ranges',
  'last-modified',
  'etag',
]);

async function handleCdn(req, res, incoming) {
  const targetUrl = incoming.searchParams.get('url');
  const referer =
    incoming.searchParams.get('referer') || `https://${DEFAULT_UPSTREAM_HOST}/`;

  if (!targetUrl) {
    res.writeHead(400, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'missing url param' }));
    return;
  }

  let parsed;
  try {
    parsed = new URL(targetUrl);
  } catch {
    res.writeHead(400, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'invalid url' }));
    return;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    res.writeHead(400).end('bad scheme');
    return;
  }
  // Strict allowlist — don't turn this into an open proxy.
  if (!parsed.hostname.toLowerCase().endsWith(CDN_ALLOWED_HOST_SUFFIX)) {
    res.writeHead(403, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'host not allowed', host: parsed.hostname }));
    return;
  }

  const headers = {
    'User-Agent': BROWSER_UA,
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': referer,
    'Origin': new URL(referer).origin,
    // Some Aliyun OSS edges 406 on identity if upstream is gzipped, but the
    // CDN serves raw mp4 — identity keeps us out of decode loops.
    'Accept-Encoding': 'identity',
  };
  // Forward Range so the player can seek.
  if (req.headers['range']) headers['Range'] = req.headers['range'];

  let upstream;
  try {
    upstream = await fetch(targetUrl, { method: req.method, headers });
  } catch (err) {
    const cause = err.cause
      ? `${err.cause.code || ''} ${err.cause.message || err.cause}`
      : '';
    console.log(`CDN UPSTREAM ERROR ${parsed.hostname} msg=${err.message} cause=${cause}`);
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'upstream_failed', message: err.message }));
    return;
  }

  if (upstream.status >= 400) {
    // Log a snippet so we can see if it's IP-block, signature expiry, etc.
    const text = await upstream.clone().text().catch(() => '<unreadable>');
    console.log(
      `CDN UPSTREAM ${upstream.status} ${parsed.hostname}${parsed.pathname} body=${text.slice(0, 300)}`,
    );
  }

  const outHeaders = {};
  upstream.headers.forEach((v, k) => {
    if (CDN_PASSTHROUGH_HEADERS.has(k.toLowerCase())) outHeaders[k] = v;
  });
  res.writeHead(upstream.status, outHeaders);

  if (req.method === 'HEAD' || !upstream.body) {
    res.end();
    return;
  }
  // Stream chunks straight to the client — never buffer the whole body, video
  // files run multiple GB.
  try {
    await pipeline(Readable.fromWeb(upstream.body), res);
  } catch (err) {
    // Client disconnected mid-stream is normal (user paused/closed). Other
    // errors are worth a log line.
    if (err.code !== 'ERR_STREAM_PREMATURE_CLOSE' && err.code !== 'EPIPE') {
      console.log(`CDN PIPE ERROR ${parsed.hostname} msg=${err.message}`);
    }
  }
}

const server = createServer(async (req, res) => {
  // Health check — Fly hits this; also useful for sanity testing post-deploy.
  if (req.url === '/' || req.url === '/healthz') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, region: process.env.FLY_REGION || 'unknown' }));
    return;
  }

  const incoming = new URL(req.url, `http://${req.headers.host}`);

  // Auth gate applies to every proxied path.
  if (PROXY_SECRET && req.headers['x-auth'] !== PROXY_SECRET) {
    res.writeHead(401).end('unauthorized');
    return;
  }

  if (incoming.pathname === '/cdn') {
    await handleCdn(req, res, incoming);
    return;
  }

  if (!incoming.pathname.startsWith('/wefeed-h5api-bff/')) {
    res.writeHead(404).end('not a proxied path');
    return;
  }

  const upstreamHost = req.headers['x-upstream-host'] || DEFAULT_UPSTREAM_HOST;
  const upstreamReferer = req.headers['x-upstream-referer'] || `https://${upstreamHost}/`;
  const upstreamUrl = `https://${upstreamHost}${incoming.pathname}${incoming.search}`;

  const headers = {
    'Accept': req.headers['accept'] || 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'User-Agent': BROWSER_UA,
    'X-Client-Info': '{"timezone":"Africa/Nairobi"}',
    'X-Source': '',
    'Referer': upstreamReferer,
    'Cookie': `uuid=${randomUUID()}`,
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
  };

  try {
    const upstream = await fetch(upstreamUrl, { method: req.method, headers });

    if (upstream.status >= 400) {
      const text = await upstream.clone().text().catch(() => '<unreadable>');
      console.log(`UPSTREAM ${upstream.status} ${upstreamUrl} body=${text.slice(0, 500)}`);
    }

    // Pass through status + most headers, drop encoding/length (fetch decoded).
    const out = {};
    upstream.headers.forEach((v, k) => {
      if (k === 'content-encoding' || k === 'content-length' || k === 'transfer-encoding') return;
      out[k] = v;
    });
    res.writeHead(upstream.status, out);
    if (upstream.body) {
      const buf = Buffer.from(await upstream.arrayBuffer());
      res.end(buf);
    } else {
      res.end();
    }
  } catch (err) {
    // Node's fetch wraps the real reason in err.cause — surface it.
    const cause = err.cause ? `${err.cause.code || ''} ${err.cause.message || err.cause}` : '';
    console.log(`UPSTREAM ERROR ${upstreamUrl} msg=${err.message} cause=${cause}`);
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({
      error: 'upstream_failed',
      message: err.message,
      cause: cause || undefined,
    }));
  }
});

server.listen(PORT, () => {
  console.log(`moviebox-proxy listening on ${PORT} (region=${process.env.FLY_REGION || 'local'})`);
});
