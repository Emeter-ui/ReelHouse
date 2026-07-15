/**
 * Custom hianime.ms scraper. The full Consumet stack broke in 2026 (upstream
 * repo DMCA'd, aniwatch's parsers point at the dead hianime.to layout), so
 * we scrape hianime.ms directly — it's a different fork with its own schema
 * but is directly reachable from Fly Singapore without Cloudflare gating.
 *
 * Streaming strategy: hianime.ms plays through iframe embeds
 * (megaplay.buzz, vidnest.fun). The real .m3u8 is fetched by the player's
 * own JS after page load, protected by rotating encryption. We return the
 * embed URL and the frontend renders it in an <iframe> — no decryption to
 * maintain, and the embed player handles quality/ads/subs itself.
 *
 * Route shape matches what reelhouse-backend already expects:
 *   GET /anime/:provider/:query        → search
 *   GET /anime/:provider/info?id=…
 *   GET /anime/:provider/watch/:epId?server=&type=
 */
const express = require('express')
const cors = require('cors')
const axios = require('axios')
const cheerio = require('cheerio')

const PORT = Number(process.env.PORT || 3000)
const BASE = (process.env.ANIWATCH_DOMAIN ? `https://${process.env.ANIWATCH_DOMAIN}` : 'https://hianime.ms').replace(/\/$/, '')

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
const HEADERS = { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml' }
const HIANIME_ALIASES = new Set(['hianime', 'zoro'])

async function httpGet(url) {
  const r = await axios.get(url, { headers: HEADERS, timeout: 20000, maxRedirects: 5 })
  return r.data
}

function parseSearchHtml(html) {
  const $ = cheerio.load(html)
  const results = []
  $('.film_list-wrap .flw-item').each((_, el) => {
    const $el = $(el)
    const a = $el.find('.film-name a')
    const href = a.attr('href') || ''
    // href format: https://hianime.ms/details/{slug} — slug is our id.
    const slug = href.replace(/^https?:\/\/[^/]+\/details\//, '').replace(/\?.*$/, '')
    if (!slug) return
    const fdi = $el.find('.fdi-item, .fd-infor .fdi-item').map((_, x) => $(x).text().trim()).get()
    results.push({
      id: slug,
      title: a.text().trim() || slug,
      image: `${BASE}/images/poster/${slug}.webp`,
      type: fdi[0] || null,
      releaseDate: null,
      subOrDub: (fdi.join(' ').match(/\b(sub|dub)\b/i) || [null])[0]?.toLowerCase() || null,
    })
  })
  // hianime.ms pagination: look for .pagination .active + .page-item or similar.
  // Falling back: if we returned any results, assume hasNextPage=true optimistically.
  const hasNextPage = $('.pagination .page-item.active').length > 0 &&
    $('.pagination .page-item.active').next('.page-item').length > 0
  return { hasNextPage, results }
}

/**
 * Details/info scrape.
 *
 * hianime.ms's /details page has metadata but NOT the episode list — that
 * lives on the /watch-… pages, keyed on a stream token embedded in
 * `.ws-ep[data-stream-token]`. So we do a two-hop: detail page for
 * title/description, then episode 1's watch page for the full episode list
 * and the AniList/MAL ids used for player fallbacks.
 */
async function scrapeInfo(slug) {
  const detailsUrl = `${BASE}/details/${slug}`
  const detailsHtml = await httpGet(detailsUrl)
  const $d = cheerio.load(detailsHtml)

  const title =
    $d('meta[property="og:title"]').attr('content')?.split(' - ')[0]?.trim() ||
    $d('title').text().split(' - ')[0]?.trim() ||
    slug
  const description = $d('meta[property="og:description"]').attr('content') || null
  const image = `${BASE}/images/poster/${slug}.webp`

  // First watch link on the page — the "Watch Now" button and episode-list links
  // all follow /watch-<slug>-episode-1-<hash> shape. Anything with `watch-`
  // in the href is a candidate.
  let watchUrl = null
  $d('a[href*="/watch-"]').each((_, el) => {
    if (watchUrl) return
    const href = $d(el).attr('href') || ''
    if (href.includes('/watch-')) watchUrl = href.startsWith('http') ? href : `${BASE}${href}`
  })

  if (!watchUrl) {
    return {
      id: slug,
      title,
      image,
      description,
      releaseDate: null,
      status: null,
      totalEpisodes: 0,
      genres: [],
      episodes: [],
    }
  }

  const watchHtml = await httpGet(watchUrl)
  const $w = cheerio.load(watchHtml)

  // Ids we need for the megaplay iframe URL builder later.
  const anilistIdMatch = watchHtml.match(/anilistId\s*=\s*(\d+)/)
  const malIdMatch = watchHtml.match(/malId\s*=\s*(\d+)/)
  const anilistId = anilistIdMatch ? Number(anilistIdMatch[1]) : null
  const malId = malIdMatch ? Number(malIdMatch[1]) : null

  const episodes = []
  $w('.ws-ep').each((_, el) => {
    const $el = $w(el)
    const num = parseInt($el.attr('data-episode') || '', 10)
    const url = $el.attr('data-url') || ''
    const streamToken = $el.attr('data-stream-token') || ''
    if (!Number.isFinite(num) || !url) return
    // Composite id encodes everything the stream endpoint needs — no per-play
    // re-scrape of the watch page. `|` chosen because streamToken is base64
    // (only A–Z, a–z, 0–9, +, /, =, -, _) and can't collide.
    const compositeId = [slug, String(num), streamToken || '', anilistId || '', malId || ''].join('|')
    episodes.push({
      id: compositeId,
      number: num,
      title: $el.attr('title') || null,
      isFiller: false,
    })
  })

  return {
    id: slug,
    title,
    image,
    description,
    releaseDate: null,
    status: null,
    totalEpisodes: episodes.length || null,
    genres: [],
    episodes,
    anilistId,
    malId,
  }
}

/**
 * Stream resolve. Returns the megaplay iframe embed URL rather than a raw
 * m3u8 — see file header for reasoning. Fallback chain matches the one
 * baked into hianime.ms's own player:
 *   1. hianime episode id (via decoded stream token)
 *   2. AniList id + episode number
 *   3. MAL id + episode number
 */
function parseCompositeId(compositeId) {
  const [slug, epStr, streamToken, anilistStr, malStr] = compositeId.split('|')
  return {
    slug,
    episode: Number(epStr) || 1,
    streamToken: streamToken || '',
    anilistId: Number(anilistStr) || null,
    malId: Number(malStr) || null,
  }
}

function buildMegaplayUrl(parsed, version) {
  const v = version === 'dub' ? 'dub' : 'sub'
  // 1) hianime episode id (best — most stable, direct lookup)
  if (parsed.streamToken) {
    try {
      const b64 = parsed.streamToken.replace(/-/g, '+').replace(/_/g, '/')
      const decoded = Buffer.from(b64, 'base64').toString('utf8')
      const epId = decoded.split(':')[0]
      if (epId) return `https://megaplay.buzz/stream/s-2/${epId}/${v}`
    } catch (_) { /* fall through */ }
  }
  // 2) AniList id + episode number
  if (parsed.anilistId) return `https://megaplay.buzz/stream/ani/${parsed.anilistId}/${parsed.episode}/${v}`
  // 3) MAL id + episode number
  if (parsed.malId) return `https://megaplay.buzz/stream/mal/${parsed.malId}/${parsed.episode}/${v}`
  return null
}

function buildVidnestUrl(parsed, version) {
  const v = version === 'dub' ? 'dub' : 'sub'
  if (!parsed.anilistId) return null
  return `https://vidnest.fun/anime/${parsed.anilistId}/${parsed.episode}/${v}`
}

// ---------------------------------------------------------------- app ----

const app = express()
app.use(cors())
app.disable('x-powered-by')

app.get('/', (_req, res) => {
  res.json({
    name: 'reelhouse-consumet',
    providers: ['hianime', 'zoro'],
    note: 'Custom hianime.ms scraper. zoro is aliased to hianime.',
    upstream: BASE,
    streaming: 'iframe embed (megaplay.buzz + vidnest.fun fallback)',
  })
})

app.get('/health', (_req, res) => res.json({ ok: true }))

function unknownProvider(res, provider) {
  return res.status(501).json({ error: 'provider not implemented', provider })
}

app.get('/anime/:provider/info', async (req, res) => {
  if (!HIANIME_ALIASES.has(String(req.params.provider).toLowerCase())) {
    return unknownProvider(res, req.params.provider)
  }
  const id = String(req.query.id || '')
  if (!id) return res.status(400).json({ error: 'missing id' })
  try {
    const data = await scrapeInfo(id)
    res.json(data)
  } catch (e) {
    res.status(502).json({ error: 'upstream', detail: String(e?.message || e) })
  }
})

app.get('/anime/:provider/watch/:episodeId', async (req, res) => {
  if (!HIANIME_ALIASES.has(String(req.params.provider).toLowerCase())) {
    return unknownProvider(res, req.params.provider)
  }
  const compositeId = decodeURIComponent(req.params.episodeId || '')
  if (!compositeId) return res.status(400).json({ error: 'missing episodeId' })
  const version = req.query.type === 'dub' ? 'dub' : 'sub'
  try {
    const parsed = parseCompositeId(compositeId)
    // Order matters: `sources[0]` becomes the frontend's default iframe src.
    // Vidnest first because megaplay 410s aggressively on per-episode file
    // takedowns ("removed due to copyright violation"), while vidnest
    // aggregates several backends behind the AniList id and holds up better.
    const vidnest = buildVidnestUrl(parsed, version)
    const megaplay = buildMegaplayUrl(parsed, version)
    const sources = []
    if (vidnest) sources.push({ url: vidnest, isM3U8: false, quality: 'HD', type: 'iframe', server: 'vidnest' })
    if (megaplay) sources.push({ url: megaplay, isM3U8: false, quality: 'HD', type: 'iframe', server: 'megaplay' })
    if (!sources.length) return res.status(404).json({ error: 'no source', detail: 'no id chain (streamToken/anilistId/malId) resolvable' })
    res.json({
      headers: { Referer: 'https://hianime.ms/' },
      sources,
      subtitles: [],
    })
  } catch (e) {
    res.status(502).json({ error: 'upstream', detail: String(e?.message || e) })
  }
})

app.get('/anime/:provider/:query', async (req, res) => {
  if (!HIANIME_ALIASES.has(String(req.params.provider).toLowerCase())) {
    return unknownProvider(res, req.params.provider)
  }
  const query = decodeURIComponent(req.params.query || '')
  const page = Number(req.query.page || 1)
  if (!query) return res.status(400).json({ error: 'missing query' })
  try {
    const searchUrl = `${BASE}/search?keyword=${encodeURIComponent(query)}${page > 1 ? `&page=${page}` : ''}`
    const html = await httpGet(searchUrl)
    const { hasNextPage, results } = parseSearchHtml(html)
    res.json({ currentPage: page, hasNextPage, totalPages: hasNextPage ? page + 1 : page, results })
  } catch (e) {
    res.status(502).json({ error: 'upstream', detail: String(e?.message || e) })
  }
})

// Bind to :: (IPv6 wildcard) so the sibling backend can reach us over Fly's
// 6PN private network — 0.0.0.0 would only accept public IPv4 traffic and
// silently reject `.internal` calls.
app.listen(PORT, '::', () => {
  console.log(`reelhouse-consumet listening on :${PORT} (upstream ${BASE})`)
})
