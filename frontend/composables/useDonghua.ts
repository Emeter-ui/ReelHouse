/**
 * Donghua composable — talks to the FastAPI `/api/donghua/*` routes, which in
 * turn front a self-hosted Consumet API (Zoro primary, AnimeKai backup).
 *
 * These shapes are Consumet's, passed through the backend more-or-less
 * verbatim. The stream endpoint reshapes into StreamResolveResponse (from
 * useStream.ts) so the existing Player component can consume it unchanged.
 */
import type { StreamResolveResponse } from '~/composables/useStream'

export interface DonghuaSearchResult {
  id: string
  title: string
  image?: string | null
  type?: string | null
  releaseDate?: string | null
  subOrDub?: string | null
}

export interface DonghuaSearchResponse {
  provider: 'zoro' | 'animekai'
  hasNextPage: boolean
  results: DonghuaSearchResult[]
}

export interface DonghuaEpisode {
  id: string
  number: number
  title?: string | null
  isFiller?: boolean
}

export interface DonghuaInfo {
  id: string
  title: string | { romaji?: string; english?: string; native?: string }
  image?: string | null
  cover?: string | null
  description?: string | null
  releaseDate?: string | null
  status?: string | null
  totalEpisodes?: number | null
  genres?: string[]
  episodes: DonghuaEpisode[]
}

/** Backend base — same runtime config every other composable uses. */
function apiBase(): string {
  return useRuntimeConfig().public.apiBase as string
}

export async function searchDonghua(
  query: string,
  page = 1,
): Promise<DonghuaSearchResponse> {
  const url = `${apiBase()}/api/donghua/search?q=${encodeURIComponent(query)}&page=${page}`
  return await $fetch<DonghuaSearchResponse>(url)
}

export async function donghuaInfo(
  id: string,
  provider: 'zoro' | 'animekai' = 'zoro',
): Promise<DonghuaInfo> {
  const url = `${apiBase()}/api/donghua/info?id=${encodeURIComponent(id)}&provider=${provider}`
  return await $fetch<DonghuaInfo>(url)
}

export async function donghuaStream(
  episodeId: string,
  provider: 'zoro' | 'animekai' = 'zoro',
): Promise<StreamResolveResponse> {
  const url =
    `${apiBase()}/api/donghua/stream?ep=${encodeURIComponent(episodeId)}` +
    `&provider=${provider}`
  return await $fetch<StreamResolveResponse>(url)
}

/** Consumet's `title` can be a string OR an AniList-shaped object. Normalize. */
export function donghuaTitle(t: DonghuaInfo['title']): string {
  if (typeof t === 'string') return t
  return t?.english || t?.romaji || t?.native || 'Untitled'
}

/** Curated donghua browse row — no discovery API, so we hardcode a short list
 *  of popular titles the user asked us to focus on. Falls back gracefully if
 *  any of them aren't found on the provider. */
export const FEATURED_DONGHUA: Array<{ query: string; label: string }> = [
  { query: 'Renegade Immortal', label: 'Renegade Immortal' },
  { query: 'Swallowed Star', label: 'Swallowed Star' },
  { query: 'Soul Land', label: 'Soul Land' },
  { query: 'Soul Land 2', label: 'Soul Land 2: Peerless Tang Sect' },
  { query: 'Battle Through the Heavens', label: 'Battle Through the Heavens' },
  { query: 'A Record of a Mortals Journey to Immortality', label: 'Mortal Journey' },
  { query: 'Perfect World', label: 'Perfect World' },
  { query: 'Throne of Seal', label: 'Throne of Seal' },
]
