<script setup lang="ts">
import { tmdbImg } from '~/composables/useTmdb'

const route = useRoute()
const router = useRouter()
const { public: { apiBase } } = useRuntimeConfig()

const q = ref<string>((route.query.q as string) ?? '')
const open = ref(false)
const focused = ref(false)
const loading = ref(false)

watch(
  () => route.query.q,
  (v) => {
    q.value = (v as string) ?? ''
  },
)

type Suggestion = {
  id: number
  media_type: 'movie' | 'tv' | 'person'
  title?: string
  name?: string
  poster_path: string | null
  release_date?: string
  first_air_date?: string
}
const suggestions = ref<Suggestion[]>([])

let debounceId: ReturnType<typeof setTimeout> | null = null
let activeQuery = ''

watch(q, (term) => {
  const t = term.trim()
  if (debounceId) clearTimeout(debounceId)
  if (!t) {
    suggestions.value = []
    loading.value = false
    return
  }
  loading.value = true
  debounceId = setTimeout(async () => {
    activeQuery = t
    try {
      const url =
        `${apiBase}/api/tmdb/search/multi?query=${encodeURIComponent(t)}` +
        `&page=1&include_adult=false`
      const res = await $fetch<{ results: Suggestion[] }>(url)
      // Drop late responses for stale terms
      if (activeQuery !== t) return
      suggestions.value = (res.results ?? [])
        .filter((r) => r.media_type !== 'person' && (r.title || r.name))
        .slice(0, 8)
    } catch {
      suggestions.value = []
    } finally {
      if (activeQuery === t) loading.value = false
    }
  }, 250)
})

const links = [
  { to: '/', label: 'Home' },
  { to: '/movies', label: 'Movies' },
  { to: '/series', label: 'Series' },
  { to: '/collection', label: 'Collections' },
  { to: '/my-list', label: 'My List' },
]

const submitSearch = () => {
  const term = q.value.trim()
  if (!term) return
  router.push(`/search?q=${encodeURIComponent(term)}`)
  open.value = false
  focused.value = false
}

const goToItem = (s: Suggestion) => {
  const path = s.media_type === 'tv' ? `/series/${s.id}` : `/movie/${s.id}`
  router.push(path)
  focused.value = false
  open.value = false
}

const yearOf = (s: Suggestion) => {
  const d = s.release_date || s.first_air_date
  return d ? d.slice(0, 4) : ''
}
const titleOf = (s: Suggestion) => s.title || s.name || ''

const showDropdown = computed(
  () => focused.value && q.value.trim().length > 0,
)

const onBlur = () => {
  // Delay so click on a result fires before the dropdown unmounts.
  setTimeout(() => {
    focused.value = false
  }, 150)
}

const isActive = (to: string) =>
  to === '/' ? route.path === '/' : route.path.startsWith(to)
</script>

<template>
  <header
    class="sticky top-0 z-30 backdrop-blur bg-ink-950/70 border-b border-white/5"
  >
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center gap-6">
      <NuxtLink to="/" class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-md bg-brand-gradient" />
        <span class="font-semibold text-lg tracking-tight">Reelhouse</span>
      </NuxtLink>

      <nav class="hidden md:flex items-center gap-1 ml-4">
        <NuxtLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="px-3 py-1.5 rounded-md text-sm transition-colors"
          :class="
            isActive(l.to)
              ? 'bg-white/10 text-white'
              : 'text-slate-300 hover:text-white hover:bg-white/5'
          "
        >
          {{ l.label }}
        </NuxtLink>
      </nav>

      <form
        class="ml-auto flex items-center gap-2 relative"
        @submit.prevent="submitSearch"
      >
        <input
          v-model="q"
          type="search"
          placeholder="Search movies, series…"
          class="hidden sm:block w-64 rounded-full bg-white/5 px-4 py-2 text-sm
                 ring-1 ring-white/10 focus:ring-accent focus:bg-white/10
                 outline-none placeholder:text-slate-500"
          @focus="focused = true"
          @blur="onBlur"
          @keydown.escape="focused = false"
        />
        <button
          type="button"
          class="sm:hidden btn-ghost px-3 py-2"
          aria-label="Search"
          @click="open = !open"
        >
          🔍
        </button>

        <div
          v-if="showDropdown"
          class="hidden sm:block absolute top-full right-0 mt-2 w-96
                 max-h-[70vh] overflow-y-auto rounded-xl bg-ink-900
                 ring-1 ring-white/10 shadow-2xl"
        >
          <div v-if="loading" class="px-4 py-3 text-sm text-slate-400">
            Searching…
          </div>
          <div
            v-else-if="!suggestions.length"
            class="px-4 py-3 text-sm text-slate-400"
          >
            No results for "{{ q }}".
          </div>
          <ul v-else class="py-2">
            <li v-for="s in suggestions" :key="`${s.media_type}-${s.id}`">
              <button
                type="button"
                class="w-full text-left flex items-center gap-3 px-3 py-2 hover:bg-white/5"
                @mousedown.prevent="goToItem(s)"
              >
                <div class="w-10 h-14 rounded bg-ink-800 overflow-hidden flex-shrink-0">
                  <img
                    v-if="s.poster_path"
                    :src="tmdbImg(s.poster_path, 'w300')"
                    :alt="titleOf(s)"
                    class="w-full h-full object-cover"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="text-sm font-medium truncate">{{ titleOf(s) }}</div>
                  <div class="text-xs text-slate-400">
                    {{ s.media_type === 'tv' ? 'Series' : 'Movie' }}
                    <span v-if="yearOf(s)"> · {{ yearOf(s) }}</span>
                  </div>
                </div>
              </button>
            </li>
            <li class="border-t border-white/5 mt-1">
              <button
                type="button"
                class="w-full text-left px-3 py-2 text-sm text-accent hover:bg-white/5"
                @mousedown.prevent="submitSearch"
              >
                See all results for "{{ q }}" →
              </button>
            </li>
          </ul>
        </div>
      </form>
    </div>

    <div v-if="open" class="sm:hidden border-t border-white/5 px-6 py-3">
      <form @submit.prevent="submitSearch">
        <input
          v-model="q"
          autofocus
          type="search"
          placeholder="Search…"
          class="w-full rounded-full bg-white/5 px-4 py-2 text-sm ring-1 ring-white/10 outline-none"
        />
      </form>
      <div v-if="q.trim()" class="mt-3">
        <div v-if="loading" class="px-2 py-3 text-sm text-slate-400">
          Searching…
        </div>
        <div
          v-else-if="!suggestions.length"
          class="px-2 py-3 text-sm text-slate-400"
        >
          No results.
        </div>
        <ul v-else class="space-y-1">
          <li v-for="s in suggestions" :key="`${s.media_type}-${s.id}`">
            <button
              type="button"
              class="w-full text-left flex items-center gap-3 px-2 py-2 rounded hover:bg-white/5"
              @click="goToItem(s)"
            >
              <div class="w-10 h-14 rounded bg-ink-800 overflow-hidden flex-shrink-0">
                <img
                  v-if="s.poster_path"
                  :src="tmdbImg(s.poster_path, 'w300')"
                  :alt="titleOf(s)"
                  class="w-full h-full object-cover"
                />
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium truncate">{{ titleOf(s) }}</div>
                <div class="text-xs text-slate-400">
                  {{ s.media_type === 'tv' ? 'Series' : 'Movie' }}
                  <span v-if="yearOf(s)"> · {{ yearOf(s) }}</span>
                </div>
              </div>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </header>
</template>
