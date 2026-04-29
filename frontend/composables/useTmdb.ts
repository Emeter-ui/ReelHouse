import type { Ref } from 'vue'

type ReactiveString = string | Ref<string> | (() => string)
type QueryValue = string | number | boolean | undefined | null
type ReactiveQuery =
  | Record<string, QueryValue>
  | Ref<Record<string, QueryValue>>
  | (() => Record<string, QueryValue>)

function unwrap<T>(v: T | Ref<T> | (() => T)): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as object)) return (v as Ref<T>).value
  return v as T
}

/**
 * Thin wrapper over `useFetch` that proxies through the backend's
 * /api/tmdb/{path} catch-all. Accepts plain or reactive path/query;
 * useFetch refetches automatically when either changes.
 */
export function useTmdb<T = unknown>(
  path: ReactiveString,
  query: ReactiveQuery = {},
  opts: { lazy?: boolean } = {},
) {
  const { public: { apiBase } } = useRuntimeConfig()

  const url = () => {
    const p = unwrap(path).replace(/^\//, '')
    return `${apiBase}/api/tmdb/${p}`
  }

  const cleanedQuery = () => {
    const q = unwrap(query)
    return Object.fromEntries(
      Object.entries(q).filter(([, v]) => v !== undefined && v !== '' && v !== null),
    )
  }

  return useFetch<T>(url, {
    query: cleanedQuery,
    lazy: opts.lazy ?? false,
    server: false,
  })
}

export function tmdbImg(path: string | null | undefined, size: 'w300' | 'w500' | 'w780' | 'original' = 'w500') {
  if (!path) return ''
  const { public: { tmdbImageBase } } = useRuntimeConfig()
  return `${tmdbImageBase}/${size}${path}`
}
