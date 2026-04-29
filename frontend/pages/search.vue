<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const q = computed(() => (route.query.q as string) ?? '')

useHead({ title: () => (q.value ? `Search: ${q.value}` : 'Search — Reelhouse') })

type SearchItem = {
  id: number
  media_type: 'movie' | 'tv' | 'person'
  title?: string
  name?: string
  poster_path: string | null
  profile_path: string | null
  release_date?: string
  first_air_date?: string
  vote_average?: number
}

const filter = ref<'all' | 'movie' | 'tv'>('all')
const filterOptions = [
  { key: 'all', label: 'All' },
  { key: 'movie', label: 'Movies' },
  { key: 'tv', label: 'Series' },
]

const { data, pending } = await useTmdb<{ results: SearchItem[] }>(
  () =>
    filter.value === 'all'
      ? 'search/multi'
      : filter.value === 'movie'
        ? 'search/movie'
        : 'search/tv',
  () => ({ query: q.value, page: 1, include_adult: 'false' }),
  { lazy: true },
)

const results = computed(() =>
  (data.value?.results ?? []).filter((r) => r.media_type !== 'person' || filter.value === 'all'),
)

// keep input in sync with URL (for typing in /search directly)
const localQ = ref(q.value)
watch(q, (v) => (localQ.value = v))

const submit = () => {
  if (!localQ.value.trim()) return
  router.replace(`/search?q=${encodeURIComponent(localQ.value.trim())}`)
}

const yearOf = (i: SearchItem) => {
  const d = i.release_date || i.first_air_date
  return d ? Number(d.slice(0, 4)) : null
}
const titleOf = (i: SearchItem) => i.title || i.name || 'Untitled'
const typeOf = (i: SearchItem): 'movie' | 'series' =>
  i.media_type === 'tv' || filter.value === 'tv' ? 'series' : 'movie'
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 py-8">
    <h1 class="text-2xl font-bold mb-4">Search</h1>

    <form class="mb-6" @submit.prevent="submit">
      <input
        v-model="localQ"
        type="search"
        placeholder="Search movies and series…"
        class="w-full max-w-xl rounded-full bg-white/5 px-5 py-3 text-base ring-1 ring-white/10 outline-none focus:ring-accent"
      />
    </form>

    <div class="mb-6">
      <CategoryFilter v-model="filter" :options="filterOptions" />
    </div>

    <div v-if="!q" class="text-slate-400 py-12 text-center">Type something to search.</div>
    <div v-else-if="pending && !data" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      <div v-for="i in 10" :key="i" class="aspect-[2/3] rounded-lg bg-white/5 animate-pulse" />
    </div>
    <div v-else-if="!results.length" class="text-slate-400 py-12 text-center">
      No results for "{{ q }}".
    </div>
    <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      <MovieCard
        v-for="r in results"
        :key="`${r.media_type}-${r.id}`"
        :id="r.id"
        :type="typeOf(r)"
        :title="titleOf(r)"
        :poster="r.poster_path"
        :year="yearOf(r)"
        :rating="r.vote_average ?? null"
        size="sm"
      />
    </div>
  </div>
</template>
