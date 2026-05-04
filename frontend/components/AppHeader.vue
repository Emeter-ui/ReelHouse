<script setup lang="ts">
import { tmdbImg } from '~/composables/useTmdb'

const route = useRoute()
const router = useRouter()
const { public: { apiBase } } = useRuntimeConfig()

const q = ref<string>((route.query.q as string) ?? '')
const searchOpen = ref(false)
const menuOpen = ref(false)
const focused = ref(false)
const loading = ref(false)

// Close menu/search on route change
watch(() => route.fullPath, () => {
  menuOpen.value = false
  searchOpen.value = false
})

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
  searchOpen.value = false
  focused.value = false
}

const goToItem = (s: Suggestion) => {
  const path = s.media_type === 'tv' ? `/series/${s.id}` : `/movie/${s.id}`
  router.push(path)
  focused.value = false
  searchOpen.value = false
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
  setTimeout(() => {
    focused.value = false
  }, 150)
}

const isActive = (to: string) =>
  to === '/' ? route.path === '/' : route.path.startsWith(to)
</script>

<template>
  <header
    class="sticky top-0 z-50 transition-all duration-300"
    :class="[
      menuOpen || searchOpen ? 'bg-ink-950' : 'backdrop-blur-md bg-ink-950/80 border-b border-white/5'
    ]"
  >
    <div class="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-4 sm:gap-8">
      <!-- Mobile Menu Toggle -->
      <button
        class="md:hidden w-10 h-10 flex flex-col items-center justify-center gap-1.5 transition-colors text-slate-300 hover:text-white"
        @click="menuOpen = !menuOpen"
      >
        <div class="w-5 h-0.5 bg-current transition-transform duration-300" :class="menuOpen ? 'rotate-45 translate-y-2' : ''" />
        <div class="w-5 h-0.5 bg-current transition-opacity" :class="menuOpen ? 'opacity-0' : ''" />
        <div class="w-5 h-0.5 bg-current transition-transform duration-300" :class="menuOpen ? '-rotate-45 -translate-y-2' : ''" />
      </button>

      <!-- Logo -->
      <NuxtLink to="/" class="flex items-center gap-2.5 group">
        <div class="w-8 h-8 rounded-lg bg-brand-gradient shadow-lg shadow-accent/20 group-hover:scale-110 transition-transform" />
        <span class="font-bold text-xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
          Reelhouse
        </span>
      </NuxtLink>

      <!-- Desktop Nav -->
      <nav class="hidden md:flex items-center gap-1">
        <NuxtLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="px-4 py-2 rounded-lg text-sm font-medium transition-all"
          :class="
            isActive(l.to)
              ? 'bg-white/10 text-white shadow-sm ring-1 ring-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          "
        >
          {{ l.label }}
        </NuxtLink>
      </nav>

      <!-- Search -->
      <div class="ml-auto flex items-center gap-2">
        <form
          class="hidden sm:block relative group"
          @submit.prevent="submitSearch"
        >
          <div class="absolute inset-y-0 left-3 flex items-center pointer-events-none text-slate-500 group-focus-within:text-accent transition-colors">
            <span class="text-sm">🔍</span>
          </div>
          <input
            v-model="q"
            type="search"
            placeholder="Search..."
            class="w-48 md:w-64 pl-10 pr-4 py-2 rounded-full bg-white/5 text-sm
                   ring-1 ring-white/10 focus:ring-accent focus:bg-white/10 focus:w-80
                   outline-none placeholder:text-slate-500 transition-all duration-300"
            @focus="focused = true"
            @blur="onBlur"
            @keydown.escape="focused = false"
          />

          <!-- Desktop Search Dropdown -->
          <Transition
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="translate-y-1 opacity-0"
            enter-to-class="translate-y-0 opacity-100"
            leave-active-class="transition duration-150 ease-in"
            leave-from-class="translate-y-0 opacity-100"
            leave-to-class="translate-y-1 opacity-0"
          >
            <div
              v-if="showDropdown"
              class="absolute top-full right-0 mt-3 w-[400px] max-h-[70vh] overflow-y-auto 
                     rounded-2xl bg-ink-900 ring-1 ring-white/10 shadow-2xl backdrop-blur-xl"
            >
              <div v-if="loading" class="px-6 py-8 text-center text-slate-400">
                <div class="w-6 h-6 border-2 border-accent/20 border-t-accent rounded-full animate-spin mx-auto mb-2" />
                <span class="text-xs uppercase tracking-widest font-semibold">Searching...</span>
              </div>
              <div
                v-else-if="!suggestions.length"
                class="px-6 py-8 text-center text-slate-500 italic"
              >
                No results found for "{{ q }}"
              </div>
              <ul v-else class="py-2">
                <li v-for="s in suggestions" :key="`${s.media_type}-${s.id}`">
                  <button
                    type="button"
                    class="w-full text-left flex items-center gap-4 px-4 py-3 hover:bg-white/5 transition-colors"
                    @mousedown.prevent="goToItem(s)"
                  >
                    <div class="w-12 h-16 rounded-lg bg-ink-800 overflow-hidden flex-shrink-0 shadow-md">
                      <img
                        v-if="s.poster_path"
                        :src="tmdbImg(s.poster_path, 'w300')"
                        :alt="titleOf(s)"
                        class="w-full h-full object-cover"
                      />
                      <div v-else class="w-full h-full flex items-center justify-center text-xs text-slate-600">🎬</div>
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="text-sm font-semibold truncate text-slate-100">{{ titleOf(s) }}</div>
                      <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
                        <span class="px-1.5 py-0.5 rounded bg-white/5 text-[10px] uppercase font-bold">{{ s.media_type === 'tv' ? 'Series' : 'Movie' }}</span>
                        <span v-if="yearOf(s)">{{ yearOf(s) }}</span>
                      </div>
                    </div>
                  </button>
                </li>
                <li class="border-t border-white/5 mt-1">
                  <button
                    type="button"
                    class="w-full text-center px-4 py-3 text-xs font-bold uppercase tracking-widest text-accent hover:bg-accent/5 transition-colors"
                    @mousedown.prevent="submitSearch"
                  >
                    See all results for "{{ q }}" →
                  </button>
                </li>
              </ul>
            </div>
          </Transition>
        </form>

        <button
          class="sm:hidden w-10 h-10 flex items-center justify-center rounded-full text-slate-300 hover:text-white transition-colors"
          @click="searchOpen = !searchOpen"
        >
          <span class="text-xl">{{ searchOpen ? '✕' : '🔍' }}</span>
        </button>
      </div>
    </div>

    <!-- Mobile Search Overlay -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="-translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="-translate-y-4 opacity-0"
    >
      <div v-if="searchOpen" class="sm:hidden border-t border-white/5 px-4 py-4 bg-ink-950">
        <form @submit.prevent="submitSearch">
          <input
            v-model="q"
            autofocus
            type="search"
            placeholder="Search movies, series..."
            class="w-full rounded-xl bg-white/5 px-5 py-3 text-base ring-1 ring-white/10 outline-none focus:ring-accent transition-all"
          />
        </form>
        <div v-if="q.trim()" class="mt-4">
          <ul v-if="suggestions.length" class="space-y-2">
            <li v-for="s in suggestions" :key="`${s.media_type}-${s.id}`">
              <button
                type="button"
                class="w-full text-left flex items-center gap-4 px-3 py-2 rounded-xl hover:bg-white/5 transition-colors"
                @click="goToItem(s)"
              >
                <div class="w-12 h-16 rounded-lg bg-ink-800 overflow-hidden flex-shrink-0 shadow-md">
                  <img
                    v-if="s.poster_path"
                    :src="tmdbImg(s.poster_path, 'w300')"
                    :alt="titleOf(s)"
                    class="w-full h-full object-cover"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="text-sm font-semibold truncate">{{ titleOf(s) }}</div>
                  <div class="text-xs text-slate-400 mt-0.5">
                    {{ s.media_type === 'tv' ? 'Series' : 'Movie' }}
                    <span v-if="yearOf(s)"> · {{ yearOf(s) }}</span>
                  </div>
                </div>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </Transition>

    <!-- Mobile Navigation Drawer -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="-translate-x-full"
      enter-to-class="translate-x-0"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="translate-x-0"
      leave-to-class="-translate-x-full"
    >
      <div v-if="menuOpen" class="md:hidden fixed inset-0 top-16 z-40 bg-ink-950 overflow-y-auto">
        <nav class="px-6 py-8 flex flex-col gap-2">
          <NuxtLink
            v-for="l in links"
            :key="l.to"
            :to="l.to"
            class="px-6 py-4 rounded-2xl text-lg font-semibold transition-all"
            :class="
              isActive(l.to)
                ? 'bg-brand-gradient text-white shadow-lg'
                : 'text-slate-300 hover:text-white hover:bg-white/5'
            "
          >
            {{ l.label }}
          </NuxtLink>
        </nav>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
/* Ensure the input search clear button doesn't mess with padding */
input[type="search"]::-webkit-search-cancel-button {
  -webkit-appearance: none;
  display: none;
}
</style>
