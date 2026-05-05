/**
 * Thin GraphQL helper for AniList. No auth required for public queries; rate
 * limit is generous (~90 req/min). We POST directly from the browser — AniList
 * permits CORS, so no backend proxy is needed.
 */
const ANILIST_URL = 'https://graphql.anilist.co'

export interface AnilistTitle {
  romaji?: string | null
  english?: string | null
  native?: string | null
}

export interface AnilistImage {
  large?: string | null
  extraLarge?: string | null
  medium?: string | null
}

export interface AnilistMediaSummary {
  id: number
  title: AnilistTitle
  coverImage: AnilistImage
  bannerImage?: string | null
  seasonYear?: number | null
  averageScore?: number | null
  episodes?: number | null
  format?: string | null
  status?: string | null
}

export interface AnilistMediaDetail extends AnilistMediaSummary {
  description?: string | null
  duration?: number | null
  genres?: string[]
  studios?: { nodes: { name: string }[] }
  startDate?: { year: number | null; month: number | null; day: number | null }
  nextAiringEpisode?:
    | { episode: number; airingAt: number; timeUntilAiring: number }
    | null
}

export interface AnilistPage<T> {
  pageInfo: {
    currentPage: number
    lastPage: number
    hasNextPage: boolean
    total: number
  }
  media: T[]
}

export async function anilistQuery<T = unknown>(
  query: string,
  variables?: Record<string, unknown>,
): Promise<T> {
  const res = await $fetch<{ data: T; errors?: Array<{ message: string }> }>(
    ANILIST_URL,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: { query, variables },
    },
  )
  if (res.errors?.length) {
    throw new Error(`AniList: ${res.errors[0].message}`)
  }
  return res.data
}

const SUMMARY_FIELDS = `
  id
  title { romaji english native }
  coverImage { large medium extraLarge }
  bannerImage
  seasonYear
  averageScore
  episodes
  format
  status
`

/** Best displayable title — prefers English, then romaji, then native. */
export const animeTitle = (t: AnilistTitle | undefined | null): string =>
  t?.english || t?.romaji || t?.native || 'Untitled'

/** Title to use when querying MovieBox — English when available (matches what
 * MovieBox indexes), otherwise romaji as fallback. */
export const animeSearchTitle = (t: AnilistTitle | undefined | null): string =>
  t?.english || t?.romaji || t?.native || ''

const BROWSE_QUERY = `
query Browse(
  $page: Int = 1
  $perPage: Int = 20
  $sort: [MediaSort] = [POPULARITY_DESC]
  $year: Int
  $season: MediaSeason
  $status: MediaStatus
) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { currentPage lastPage hasNextPage total }
    media(
      type: ANIME
      sort: $sort
      seasonYear: $year
      season: $season
      status: $status
      isAdult: false
    ) {
      ${SUMMARY_FIELDS}
    }
  }
}`

export async function browseAnime(
  variables: {
    page?: number
    perPage?: number
    sort?: string[]
    year?: number
    season?: 'WINTER' | 'SPRING' | 'SUMMER' | 'FALL'
    status?: 'FINISHED' | 'RELEASING' | 'NOT_YET_RELEASED' | 'CANCELLED' | 'HIATUS'
  } = {},
) {
  const { Page } = await anilistQuery<{ Page: AnilistPage<AnilistMediaSummary> }>(
    BROWSE_QUERY,
    variables,
  )
  return Page
}

const RECENT_QUERY = `
query RecentlyAired($perPage: Int = 20) {
  Page(page: 1, perPage: $perPage) {
    media(
      type: ANIME
      sort: [START_DATE_DESC]
      status_in: [RELEASING, FINISHED]
      isAdult: false
    ) {
      ${SUMMARY_FIELDS}
    }
  }
}`

export async function recentAnime(perPage = 20) {
  const { Page } = await anilistQuery<{ Page: AnilistPage<AnilistMediaSummary> }>(
    RECENT_QUERY,
    { perPage },
  )
  return Page.media
}

const DETAIL_QUERY = `
query Detail($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    title { romaji english native }
    description(asHtml: false)
    coverImage { large medium extraLarge }
    bannerImage
    season seasonYear
    episodes
    duration
    status
    averageScore
    genres
    format
    studios { nodes { name } }
    startDate { year month day }
    nextAiringEpisode { episode airingAt timeUntilAiring }
  }
}`

export async function animeDetail(id: number) {
  const { Media } = await anilistQuery<{ Media: AnilistMediaDetail }>(
    DETAIL_QUERY,
    { id },
  )
  return Media
}
