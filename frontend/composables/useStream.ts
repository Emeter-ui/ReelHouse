import type { Ref } from 'vue'

export interface StreamResolveResponse {
  stream_url: string
  qualities: string[]
  captions: Array<{ lang: string; url: string }>
  source: string
}

type R<T> = T | Ref<T> | (() => T)
function unwrap<T>(v: R<T>): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as object)) return (v as Ref<T>).value
  return v as T
}

export function useMovieStream(tmdbId: R<number | string>, title: R<string>, year?: R<number | undefined>) {
  const { public: { apiBase } } = useRuntimeConfig()
  return useFetch<StreamResolveResponse>(`${apiBase}/api/stream/movie`, {
    query: () => ({
      tmdb_id: unwrap(tmdbId),
      title: unwrap(title),
      year: year !== undefined ? unwrap(year) : undefined,
    }),
    server: false,
    lazy: true,
  })
}

export function useSeriesStream(
  tmdbId: R<number | string>,
  title: R<string>,
  season: R<number>,
  episode: R<number>,
) {
  const { public: { apiBase } } = useRuntimeConfig()
  return useFetch<StreamResolveResponse>(`${apiBase}/api/stream/series`, {
    query: () => ({
      tmdb_id: unwrap(tmdbId),
      title: unwrap(title),
      season: unwrap(season),
      episode: unwrap(episode),
    }),
    server: false,
    lazy: true,
  })
}

/**
 * Build a backend byte-proxy URL. Used as the fallback `<source>` when a
 * direct CDN URL fails the CORS / Referer probe.
 */
export function proxiedUrl(rawUrl: string) {
  const { public: { apiBase } } = useRuntimeConfig()
  return `${apiBase}/api/proxy?url=${encodeURIComponent(rawUrl)}`
}

/**
 * Fire a HEAD probe to decide whether the browser can fetch the URL
 * directly or whether we must route through the backend proxy.
 */
export async function canFetchDirect(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD', mode: 'cors' })
    return res.ok
  } catch {
    return false
  }
}
