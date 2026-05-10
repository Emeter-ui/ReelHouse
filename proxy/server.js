// Fly.io MovieBox H5 proxy — same logic as worker/moviebox-proxy.js but
// running on Fly so we can pin egress to a region MovieBox allows (the H5
// surface returns "invalid region" 403 from US-based hosts).
//
// Routes /wefeed-h5api-bff/* to the upstream H5 host with the Referer + uuid
// cookie MovieBox requires for non-empty stream responses.

import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';

const PORT = process.env.PORT || 8080;
const PROXY_SECRET = process.env.PROXY_SECRET || '';
const DEFAULT_UPSTREAM_HOST = 'netfilm.world';
const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

const server = createServer(async (req, res) => {
  // Health check — Fly hits this; also useful for sanity testing post-deploy.
  if (req.url === '/' || req.url === '/healthz') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, region: process.env.FLY_REGION || 'unknown' }));
    return;
  }

  const incoming = new URL(req.url, `http://${req.headers.host}`);
  if (!incoming.pathname.startsWith('/wefeed-h5api-bff/')) {
    res.writeHead(404).end('not a proxied path');
    return;
  }

  if (PROXY_SECRET && req.headers['x-auth'] !== PROXY_SECRET) {
    res.writeHead(401).end('unauthorized');
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
