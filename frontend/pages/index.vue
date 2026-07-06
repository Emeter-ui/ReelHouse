<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
import { browseAnime, animeTitle, type AnilistMediaSummary } from '~/composables/useAnilist'

useHead({ title: 'Reelhouse — Home' })

type TmdbItem = {
  id: number
  title?: string
  name?: string
  overview?: string
  backdrop_path: string | null
  poster_path: string | null
  release_date?: string
  first_air_date?: string
  vote_average?: number
  media_type?: string
}

const { data: trending } = useTmdb<{ results: TmdbItem[] }>('trending/all/week', {}, { lazy: true })
const heroItems = computed<TmdbItem[]>(() => (trending.value?.results ?? []).slice(0, 5))

// Anime row (AniList, popular).
const anime = ref<AnilistMediaSummary[] | null>(null)
const animeLoading = ref(true)
onMounted(async () => {
  try {
    const res = await browseAnime({ page: 1, perPage: 20, sort: ['POPULARITY_DESC'] })
    anime.value = res.media
  } finally {
    animeLoading.value = false
  }
})
const yearOfAnime = (a: AnilistMediaSummary) => a.seasonYear ?? null
const ratingOfAnime = (a: AnilistMediaSummary) => (a.averageScore != null ? a.averageScore / 10 : null)
</script>

<template>
  <div class="pb-20">
    <Hero :items="heroItems" class="mb-6 md:mb-10" />

    <MovieRow title="Trending Now" :items="trending?.results ?? []" />

    <MovieRow
      title="New Releases"
      type="movie"
      :tabs="[{ key: 'now_playing', label: 'In Theaters', path: 'movie/now_playing' }]"
    />

    <MovieRow
      title="Top Rated"
      type="movie"
      :tabs="[{ key: 'top_rated', label: 'Movies', path: 'movie/top_rated' }]"
    />

    <MovieRow
      title="Popular Series"
      type="series"
      :tabs="[{ key: 'popular_tv', label: 'Series', path: 'tv/popular' }]"
    />

    <MovieRow
      title="Popular Movies"
      type="movie"
      :tabs="[{ key: 'popular_movie', label: 'Movies', path: 'movie/popular' }]"
    />

    <MovieRow
      title="Comedy Movies"
      type="movie"
      :tabs="[{ key: 'comedy', label: 'Comedy', path: 'discover/movie', query: { with_genres: 35, sort_by: 'popularity.desc' } }]"
    />

    <MovieRow
      title="Action Movies"
      type="movie"
      :tabs="[{ key: 'action', label: 'Action', path: 'discover/movie', query: { with_genres: 28, sort_by: 'popularity.desc' } }]"
    />

    <!-- Anime row uses AniList data, not TMDB -->
    <section class="my-6 md:my-10 max-w-7xl mx-auto">
      <div class="px-4 sm:px-6 mb-3 md:mb-4">
        <h2 class="section-title">Animes</h2>
      </div>
      <div v-if="animeLoading" class="row-scroll px-4 sm:px-6">
        <div
          v-for="i in 8"
          :key="i"
          class="w-28 sm:w-40 md:w-48 aspect-[2/3] rounded-md bg-white/5 animate-pulse shrink-0"
        />
      </div>
      <div v-else-if="!anime?.length" class="px-4 sm:px-6 text-sm text-slate-500 py-8 text-center">
        Anime unavailable right now.
      </div>
      <div v-else class="row-scroll px-4 sm:px-6">
        <MovieCard
          v-for="a in anime"
          :key="a.id"
          :id="a.id"
          type="anime"
          :title="animeTitle(a.title)"
          :poster="a.coverImage.large || a.coverImage.medium || null"
          :year="yearOfAnime(a)"
          :rating="ratingOfAnime(a)"
        />
        <div class="w-1 shrink-0" />
      </div>
    </section>
  </div>
</template>
