import type { Ref } from 'vue'

export interface StreamOption {
  resolution: string
  size_bytes: number
  url: string
  codec?: string
  /** "" for progressive MP4, "dash" for a DASH manifest, "mp4" from the H5
   * play endpoint. The player dispatches on this. */
  format?: string
  /** For DASH variants: the height the player should lock the dash.js
   * representation to. Multiple StreamOption rows share the same .mpd URL
   * but differ in target_height. */
  target_height?: number
  /** CloudFront signed cookie string for DASH variants. The browser can't
   * set cross-origin cookies via JS, so this rides as a query param on the
   * proxy URL for both manifest and segment fetches. */
  sign_cookie?: string
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
 *
 * `isDash` lets the caller signal "this stream goes through dash.js / MSE";
 * HEVC inside MSE works wherever the browser ships an HEVC decoder
 * (Chrome 107+, Safari, Edge — Firefox returns false).
 */
export function isPlayableCodec(codec?: string, opts?: { isDash?: boolean }): boolean {
  const c = (codec ?? '').toLowerCase()
  if (!c) return true
  if (c.includes('h264') || c.includes('avc')) return true
  if (opts?.isDash && (c.includes('hevc') || c.includes('265'))) {
    return canPlayHevcMse()
  }
  return false
}

let _hevcMseCheck: boolean | null = null
/** Cached MSE.isTypeSupported probe for HEVC. Browsers without an HEVC
 * decoder (notably Firefox) say false here, so we hide DASH-HEVC streams
 * from the picker on those clients. */
export function canPlayHevcMse(): boolean {
  if (_hevcMseCheck != null) return _hevcMseCheck
  if (typeof MediaSource === 'undefined' || !MediaSource.isTypeSupported) {
    return (_hevcMseCheck = false)
  }
  _hevcMseCheck = (
    MediaSource.isTypeSupported('video/mp4; codecs="hvc1.1.6.L93.B0"') ||
    MediaSource.isTypeSupported('video/mp4; codecs="hev1.1.6.L93.B0"')
  )
  return _hevcMseCheck
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
export function proxiedUrl(
  rawUrl: string,
  referer?: string,
  downloadAs?: string,
  cookie?: string,
) {
  const { public: { apiBase } } = useRuntimeConfig()
  let url = `${apiBase}/api/proxy?url=${encodeURIComponent(rawUrl)}`
  if (referer) url += `&referer=${encodeURIComponent(referer)}`
  if (downloadAs) url += `&dl=${encodeURIComponent(downloadAs)}`
  if (cookie) url += `&cookie=${encodeURIComponent(cookie)}`
  return url
}

/**
 * Wrap a DASH manifest URL through `/api/dash-manifest`, which fetches the
 * `.mpd` with the signed CloudFront cookie + injects a `<BaseURL>` so
 * segments resolve to absolute CDN URLs (the player then runs each segment
 * fetch through `proxiedUrl` with the same cookie via an interceptor).
 */
export function dashManifestUrl(
  rawUrl: string,
  referer?: string,
  cookie?: string,
) {
  const { public: { apiBase } } = useRuntimeConfig()
  let url = `${apiBase}/api/dash-manifest?url=${encodeURIComponent(rawUrl)}`
  if (referer) url += `&referer=${encodeURIComponent(referer)}`
  if (cookie) url += `&cookie=${encodeURIComponent(cookie)}`
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
