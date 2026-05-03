<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
import { useContinueWatching } from '~/composables/useContinueWatching'
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

const movieTabs = [
  { key: 'popular', label: 'Popular', path: 'movie/popular' },
  { key: 'top_rated', label: 'Top Rated', path: 'movie/top_rated' },
  { key: 'upcoming', label: 'Upcoming', path: 'movie/upcoming' },
]
const seriesTabs = [
  { key: 'popular', label: 'Popular', path: 'tv/popular' },
  { key: 'top_rated', label: 'Top Rated', path: 'tv/top_rated' },
  { key: 'on_the_air', label: 'On TV', path: 'tv/on_the_air' },
]

const cw = useContinueWatching()
</script>

<template>
  <div>
    <Hero :items="heroItems" />

    <MovieRow
      v-if="cw.items.value.length"
      title="Continue Watching"
      :items="cw.items.value.map((i) => ({
        id: i.id,
        title: i.title,
        poster_path: i.poster,
        backdrop_path: null,
        vote_average: 0,
        media_type: i.type === 'series' ? 'tv' : 'movie',
      }))"
    />

    <MovieRow title="Trending This Week" :items="trending?.results ?? []" />
    <MovieRow title="Movies" type="movie" :tabs="movieTabs" />
    <MovieRow title="Series" type="series" :tabs="seriesTabs" />
    <MovieRow
      title="Now Playing"
      type="movie"
      :tabs="[{ key: 'now_playing', label: 'Now Playing', path: 'movie/now_playing' }]"
    />
  </div>
</template>
