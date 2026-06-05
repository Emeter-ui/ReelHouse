import type { Ref } from 'vue'

export interface StreamOption {
  resolution: string
  size_bytes: number
  url: string
  codec?: string
  format?: string
}

export interface StreamResolveResponse {
  /** May be null when only downloads are available. */
  stream_url: string | null
  stream_codec?: string
  stream_format?: string
  /** Referer the proxy should send when fetching this URL (CDN allowlists it). */
  play_referer?: string
  /** Streams playable in `<video>`. Empty if only downloads exist. */
  qualities: StreamOption[]
  /** Files from MovieBox's mobile resource endpoint. Same shape as qualities. */
  download_qualities: StreamOption[]
  captions: Array<{ lang: string; url: string }>
  source: string
}

/** Numeric height from a "1080p"-style label, or 0 if unparseable. */
export function streamHeight(resolution: string | undefined): number {
  const m = /(\d+)/.exec(resolution ?? '')
  return m ? Number(m[1]) : 0
}

/**
 * Whether a codec is safe to play (and auto-switch into) in a generic browser.
 * MovieBox's lower rungs are frequently HEVC/H.265, which throws decode-error 3
 * on engines without HEVC support — so those must never be picked automatically.
 * Unknown/empty codec is treated as playable (let the browser try).
 */
export function isPlayableCodec(codec?: string): boolean {
  const c = (codec ?? '').toLowerCase()
  if (!c) return true
  return c.includes('h264') || c.includes('avc')
}

export interface NetworkHint {
  effectiveType?: string
  saveData?: boolean
  downlink?: number
}

/** Read the Network Information API hint (absent on Safari/Firefox → {}). */
export function readNetworkHint(): NetworkHint {
  if (typeof navigator === 'undefined') return {}
  const nav = navigator as Navigator & {
    connection?: NetworkHint
    mozConnection?: NetworkHint
    webkitConnection?: NetworkHint
  }
  const c = nav.connection || nav.mozConnection || nav.webkitConnection
  if (!c) return {}
  return { effectiveType: c.effectiveType, saveData: c.saveData, downlink: c.downlink }
}

/**
 * Pick a starting resolution from a high→low sorted ladder based on the current
 * network. Returns null for an empty ladder. With no hint available (Safari,
 * Firefox) we assume a good connection and return the best rung.
 */
export function pickConnectionAwareResolution(
  ladder: StreamOption[],
  hint: NetworkHint = readNetworkHint(),
): string | null {
  if (!ladder.length) return null
  const highest = ladder[0].resolution
  const lowest = ladder[ladder.length - 1].resolution
  if (hint.saveData) return lowest
  switch (hint.effectiveType) {
    case 'slow-2g':
    case '2g':
      return lowest
    case '3g': {
      // Highest rung at or below 480p (ladder is sorted high→low, so the first
      // match is the highest); fall back to the lowest rung if none qualify.
      const cap = ladder.find((q) => streamHeight(q.resolution) <= 480)
      return (cap ?? ladder[ladder.length - 1]).resolution
    }
    default:
      // 4g or unknown — assume the best rung is sustainable.
      return highest
  }
}

type R<T> = T | Ref<T> | (() => T)
function unwrap<T>(v: R<T>): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as object)) return (v as Ref<T>).value
  return v as T
}

// Building the query string into the URL (and passing the URL as a function)
// is what makes useFetch re-evaluate when the underlying refs change. Passing
// `query: () => ({...})` alongside a static URL string was being snapshotted
// once at setup before the refs had values, sending an empty querystring and
// getting a 422 from FastAPI for missing required fields.
function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  )
  if (!entries.length) return ''
  const sp = new URLSearchParams()
  for (const [k, v] of entries) sp.set(k, String(v))
  return `?${sp.toString()}`
}

export function useMovieStream(tmdbId: R<number | string>, title: R<string>, year?: R<number | undefined>) {
  const { public: { apiBase } } = useRuntimeConfig()
  return useFetch<StreamResolveResponse>(
    () => `${apiBase}/api/stream/movie${buildQuery({
      tmdb_id: unwrap(tmdbId),
      title: unwrap(title),
      year: year !== undefined ? unwrap(year) : undefined,
    })}`,
    { server: false, lazy: true },
  )
}

export function useSeriesStream(
  tmdbId: R<number | string>,
  title: R<string>,
  season: R<number>,
  episode: R<number>,
) {
  const { public: { apiBase } } = useRuntimeConfig()
  return useFetch<StreamResolveResponse>(
    () => `${apiBase}/api/stream/series${buildQuery({
      tmdb_id: unwrap(tmdbId),
      title: unwrap(title),
      season: unwrap(season),
      episode: unwrap(episode),
    })}`,
    { server: false, lazy: true },
  )
}

/**
 * Backend-served caption URL. Fetches the upstream subtitle (typically SRT
 * from MovieBox) and converts to WebVTT, which is what `<track>` requires.
 */
export function captionsUrl(rawUrl: string) {
  const { public: { apiBase } } = useRuntimeConfig()
  return `${apiBase}/api/captions?url=${encodeURIComponent(rawUrl)}`
}

/**
 * Build a backend byte-proxy URL. Used as the fallback `<source>` when a
 * direct CDN URL fails the CORS / Referer probe. Pass `referer` so the
 * proxy can send the Referer the upstream CDN expects.
 */
export function proxiedUrl(rawUrl: string, referer?: string, downloadAs?: string) {
  const { public: { apiBase } } = useRuntimeConfig()
  let url = `${apiBase}/api/proxy?url=${encodeURIComponent(rawUrl)}`
  if (referer) url += `&referer=${encodeURIComponent(referer)}`
  if (downloadAs) url += `&dl=${encodeURIComponent(downloadAs)}`
  return url
}

/**
 * Fire a HEAD probe to decide whether the browser can fetch the URL
 * directly or whether we must route through the backend proxy.
 */
export async function canFetchDirect(url: string): Promise<boolean> {
  // If the site is HTTPS, we can't fetch HTTP directly (Mixed Content).
  if (typeof window !== 'undefined' && window.location.protocol === 'https:' && url.startsWith('http:')) {
    return false
  }

  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 3000) // 3s timeout for probe

    const res = await fetch(url, { 
      method: 'GET', 
      mode: 'cors',
      headers: { 'Range': 'bytes=0-0' },
      signal: controller.signal
    })
    clearTimeout(timer)

    // iOS requires 206 support. If we asked for a range and got 200, 
    // it's better to proxy it so we can ensure proper range handling.
    return res.status === 206
  } catch {
    return false
  }
}
