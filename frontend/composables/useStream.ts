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
