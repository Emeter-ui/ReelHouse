<script setup lang="ts">
import { useMovieStream } from '~/composables/useStream'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

type Movie = {
  id: number
  title: string
  poster_path: string | null
  release_date: string
  overview: string
}

const { data: movie } = await useTmdb<Movie>(() => `movie/${id.value}`)

useHead({ title: () => `Watching: ${movie.value?.title ?? 'Movie'}` })

const year = computed(() =>
  movie.value?.release_date ? Number(movie.value.release_date.slice(0, 4)) : undefined,
)

const { data: resolved, pending, error } = useMovieStream(
  id,
  () => movie.value?.title ?? '',
  () => year.value,
)
</script>

<template>
  <div class="min-h-screen bg-black">
    <header class="px-4 sm:px-6 py-3 flex items-center gap-3">
      <button class="btn-ghost" @click="router.back()">← Back</button>
      <div v-if="movie" class="font-medium truncate">{{ movie.title }}</div>
    </header>

    <div class="max-w-6xl mx-auto px-2 sm:px-4">
      <Player
        v-if="movie"
        :resolved="resolved"
        :pending="pending"
        :error="error"
        :content-id="movie.id"
        content-type="movie"
        :content-title="movie.title"
        :content-poster="movie.poster_path"
      />
      <div v-if="movie?.overview" class="px-2 py-4 text-sm text-slate-300 max-w-3xl">
        {{ movie.overview }}
      </div>
    </div>
  </div>
</template>
