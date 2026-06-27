<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
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

// Roll query into the URL so useFetch refetches when q/filter change.
// (useFetch reliably watches the URL getter; the separate `query` option
// does not always re-trigger on reactive changes.)
const searchPath = computed(() => {
  const sub =
    filter.value === 'all'
      ? 'search/multi'
      : filter.value === 'movie'
        ? 'search/movie'
        : 'search/tv'
  const qs = new URLSearchParams({
    query: q.value,
    page: '1',
    include_adult: 'false',
  }).toString()
  return `${sub}?${qs}`
})

const { data, pending } = await useTmdb<{ results: SearchItem[] }>(
  searchPath,
  {},
  { lazy: true },
)

const results = computed(() =>
  (data.value?.results ?? []).filter((r) => r.media_type !== 'person' || filter.value === 'all'),
)

// keep input in sync with URL (for typing in /search directly)
const localQ = ref(q.value)
watch(q, (v) => (localQ.value = v))

const { items: recentSearches, add: recordSearch, remove: removeRecent, clear: clearRecents } =
  useSearchHistory()

// Record any non-empty `?q=...` we navigate to — covers form submit, header
// submit, shared links, and back/forward (dedupe handles the noise).
watch(q, (v) => {
  if (v?.trim()) recordSearch(v.trim())
}, { immediate: true })

const submit = () => {
  const term = localQ.value.trim()
  if (!term) return
  router.replace(`/search?q=${encodeURIComponent(term)}`)
}

const useRecent = (term: string) => {
  localQ.value = term
  router.replace(`/search?q=${encodeURIComponent(term)}`)
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

    <div v-if="!q">
      <div v-if="recentSearches.length" class="max-w-xl">
        <div class="flex items-center justify-between mb-3">
          <span class="text-xs uppercase tracking-widest font-bold text-slate-500">Recent searches</span>
          <button
            type="button"
            class="text-xs uppercase tracking-widest font-bold text-slate-500 hover:text-accent transition-colors"
            @click="clearRecents()"
          >Clear all</button>
        </div>
        <ul class="flex flex-wrap gap-2">
          <li v-for="term in recentSearches" :key="term" class="flex items-stretch rounded-full bg-white/5 ring-1 ring-white/10 hover:ring-accent/40 transition">
            <button
              type="button"
              class="pl-4 pr-2 py-1.5 text-sm text-slate-200"
              @click="useRecent(term)"
            >{{ term }}</button>
            <button
              type="button"
              class="pr-3 pl-1 py-1.5 text-slate-500 hover:text-slate-200 transition-colors"
              :aria-label="`Remove ${term} from recent searches`"
              @click="removeRecent(term)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="w-3 h-3">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </li>
        </ul>
      </div>
      <div v-else class="text-slate-400 py-12 text-center">Type something to search.</div>
    </div>
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
        size="full"
      />
    </div>
  </div>
</template>
