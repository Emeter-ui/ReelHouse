<script setup lang="ts">
const route = useRoute()
const id = computed(() => Number(route.params.id))

type Part = {
  id: number
  title: string
  poster_path: string | null
  release_date?: string
  vote_average?: number
}
type Collection = {
  id: number
  name: string
  overview: string
  backdrop_path: string | null
  poster_path: string | null
  parts: Part[]
}

const { data, pending, error } = useTmdb<Collection>(
  () => `collection/${id.value}`,
  {},
  { lazy: true },
)

useHead({ title: () => `${data.value?.name ?? 'Collection'} — Reelhouse` })

const sorted = computed<Part[]>(() =>
  (data.value?.parts ?? [])
    .slice()
    .sort((a, b) => (a.release_date ?? '').localeCompare(b.release_date ?? '')),
)
</script>

<template>
  <div>
    <section v-if="data" class="relative h-[40vh] min-h-[260px] overflow-hidden">
      <img
        v-if="data.backdrop_path"
        :src="tmdbImg(data.backdrop_path, 'original')"
        :alt="data.name"
        class="absolute inset-0 w-full h-full object-cover"
      />
      <div class="absolute inset-0 bg-hero-fade" />
      <div class="relative h-full max-w-7xl mx-auto px-6 flex flex-col justify-end pb-8">
        <h1 class="text-3xl md:text-5xl font-bold tracking-tight">{{ data.name }}</h1>
        <p class="text-slate-300 line-clamp-3 max-w-2xl mt-3 text-sm md:text-base">
          {{ data.overview }}
        </p>
      </div>
    </section>

    <div class="max-w-7xl mx-auto px-6 py-8">
      <div v-if="pending && !data" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div v-for="i in 10" :key="i" class="aspect-[2/3] rounded-lg bg-white/5 animate-pulse" />
      </div>
      <div v-else-if="error" class="text-slate-400 py-12 text-center">Collection not found.</div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <MovieCard
          v-for="m in sorted"
          :key="m.id"
          :id="m.id"
          type="movie"
          :title="m.title"
          :poster="m.poster_path"
          :year="m.release_date ? Number(m.release_date.slice(0, 4)) : null"
          :rating="m.vote_average ?? null"
          size="full"
        />
      </div>
    </div>
  </div>
</template>
