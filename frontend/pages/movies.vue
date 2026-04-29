<script setup lang="ts">
useHead({ title: 'Movies — Reelhouse' })

type Movie = {
  id: number
  title: string
  poster_path: string | null
  release_date?: string
  vote_average?: number
}

const filters = ref<{ year?: number | ''; genre?: number | ''; sort?: string }>({
  year: '',
  genre: '',
  sort: 'popularity.desc',
})
const page = ref(1)

watch(filters, () => (page.value = 1), { deep: true })

const query = computed(() => ({
  sort_by: filters.value.sort || 'popularity.desc',
  primary_release_year: filters.value.year || undefined,
  with_genres: filters.value.genre || undefined,
  page: page.value,
  include_adult: 'false',
}))

const { data, pending } = await useTmdb<{
  results: Movie[]
  page: number
  total_pages: number
}>('discover/movie', () => query.value, { lazy: true })

const yearOf = (m: Movie) => (m.release_date ? Number(m.release_date.slice(0, 4)) : null)
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 py-8">
    <h1 class="text-2xl font-bold mb-6">Movies</h1>
    <div class="flex flex-col md:flex-row gap-8">
      <FilterSidebar v-model="filters" type="movie" />
      <div class="flex-1 min-w-0">
        <div v-if="pending && !data" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <div v-for="i in 15" :key="i" class="aspect-[2/3] rounded-lg bg-white/5 animate-pulse" />
        </div>
        <div v-else-if="!data?.results?.length" class="text-slate-400 py-12 text-center">
          No movies match your filters.
        </div>
        <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <MovieCard
            v-for="m in data.results"
            :key="m.id"
            :id="m.id"
            type="movie"
            :title="m.title"
            :poster="m.poster_path"
            :year="yearOf(m)"
            :rating="m.vote_average ?? null"
            size="sm"
          />
        </div>

        <div v-if="data?.total_pages && data.total_pages > 1" class="flex items-center justify-center gap-3 mt-8">
          <button
            class="btn-ghost disabled:opacity-30"
            :disabled="page <= 1"
            @click="page = Math.max(1, page - 1)"
          >
            Prev
          </button>
          <span class="text-sm text-slate-400">
            Page {{ data.page }} of {{ Math.min(data.total_pages, 500) }}
          </span>
          <button
            class="btn-ghost disabled:opacity-30"
            :disabled="page >= Math.min(data.total_pages, 500)"
            @click="page = page + 1"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
