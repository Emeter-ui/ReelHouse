import type { Ref } from 'vue'

/**
 * A single episode in MovieBox's authoritative numbering, with a source
 * (TMDB) name overlaid where one lines up — otherwise `"Episode N"`.
 */
export interface StructureEpisode {
  ep: number
  name: string
  still_path: string | null
  overview: string | null
  air_date: string | null
  runtime: number | null
}

export interface StructureSeason {
  se: number
  episodes: StructureEpisode[]
}

/**
 * The series' season/episode layout AS MOVIEBOX INDEXES IT. The frontend
 * drives its pickers from this so the (se, ep) sent to the resolver is already
 * in MovieBox's coordinate system — no cross-source numbering mismatch.
 */
export interface SeriesStructure {
  subject_id: string
  seasons: StructureSeason[]
}

type R<T> = T | Ref<T> | (() => T)
function unwrap<T>(v: R<T>): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as object)) return (v as Ref<T>).value
  return v as T
}

/**
 * Fetch the MovieBox-native season/episode structure for a series. Returns a
 * lazy, client-side `useFetch` so callers can react to load state. On any
 * failure the consumer should fall back to its source-native (TMDB/AniList)
 * layout so the page still works.
 */
export function useSeriesStructure(
  title: R<string>,
  opts: { tmdbId?: R<number | string | undefined>; anilistId?: R<number | string | undefined>; year?: R<number | string | undefined> } = {},
) {
  const { public: { apiBase } } = useRuntimeConfig()
  return useFetch<SeriesStructure>(
    () => {
      const sp = new URLSearchParams()
      const t = unwrap(title)
      sp.set('title', t ?? '')
      const tmdbId = opts.tmdbId ? unwrap(opts.tmdbId) : undefined
      const anilistId = opts.anilistId ? unwrap(opts.anilistId) : undefined
      const year = opts.year ? unwrap(opts.year) : undefined
      if (tmdbId) sp.set('tmdb_id', String(tmdbId))
      if (anilistId) sp.set('anilist_id', String(anilistId))
      if (year) sp.set('year', String(year))
      return `${apiBase}/api/series/structure?${sp.toString()}`
    },
    { server: false, lazy: true },
  )
}
