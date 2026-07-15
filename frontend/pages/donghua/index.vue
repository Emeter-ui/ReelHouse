<script setup lang="ts">
import {
  searchDonghua,
  FEATURED_DONGHUA,
  type DonghuaSearchResult,
} from '~/composables/useDonghua'

useHead({ title: 'Donghua — Reelhouse' })

// Search-driven page. Consumet has no "popular" endpoint for anime, so the
// initial view runs the featured queries in parallel and stitches together
// a curated grid. Once the user types, we swap to live search results.
const query = ref('')
const debounced = ref('')
let debounceId: ReturnType<typeof setTimeout> | null = null
watch(query, (v) => {
  if (debounceId) clearTimeout(debounceId)
  debounceId = setTimeout(() => (debounced.value = v.trim()), 300)
})

interface Card {
  id: string
  provider: 'zoro' | 'animekai'
  title: string
  image: string | null
  releaseDate?: string | null
  type?: string | null
}

const featured = ref<Card[]>([])
const featuredLoading = ref(true)

onMounted(async () => {
  featuredLoading.value = true
  try {
    const settled = await Promise.allSettled(
      FEATURED_DONGHUA.map((f) => searchDonghua(f.query, 1)),
    )
    const seen = new Set<string>()
    const items: Card[] = []
    settled.forEach((r) => {
      if (r.status !== 'fulfilled') return
      const top = r.value.results[0]
      if (!top || seen.has(top.id)) return
      seen.add(top.id)
      items.push({
        id: top.id,
        provider: r.value.provider,
        title: top.title,
        image: top.image ?? null,
        releaseDate: top.releaseDate ?? null,
        type: top.type ?? null,
      })
    })
    featured.value = items
  } finally {
    featuredLoading.value = false
  }
})

const searchResults = ref<Card[]>([])
const searchLoading = ref(false)
const searchProvider = ref<'zoro' | 'animekai' | null>(null)
let searchToken = 0

watch(debounced, async (q) => {
  const token = ++searchToken
  if (!q) {
    searchResults.value = []
    searchLoading.value = false
    searchProvider.value = null
    return
  }
  searchLoading.value = true
  try {
    const res = await searchDonghua(q, 1)
    if (token !== searchToken) return
    searchProvider.value = res.provider
    searchResults.value = res.results.map((r: DonghuaSearchResult) => ({
      id: r.id,
      provider: res.provider,
      title: r.title,
      image: r.image ?? null,
      releaseDate: r.releaseDate ?? null,
      type: r.type ?? null,
    }))
  } catch {
    if (token === searchToken) searchResults.value = []
  } finally {
    if (token === searchToken) searchLoading.value = false
  }
})

const showingSearch = computed(() => debounced.value.length > 0)
const cards = computed<Card[]>(() =>
  showingSearch.value ? searchResults.value : featured.value,
)
const loading = computed(() =>
  showingSearch.value ? searchLoading.value : featuredLoading.value,
)

const cardLink = (c: Card) =>
  `/donghua/${encodeURIComponent(c.id)}?provider=${c.provider}`
</script>

<template>
  <div class="pb-16 max-w-7xl mx-auto px-6">
    <div class="pt-8 pb-6">
      <h1 class="text-2xl font-bold tracking-tight">Donghua</h1>
      <p class="text-sm text-slate-400 mt-1">
        Chinese animation via Consumet — Zoro primary, AnimeKai backup.
      </p>
    </div>

    <div class="mb-8">
      <div class="relative max-w-lg">
        <div
          class="absolute inset-y-0 left-3 flex items-center pointer-events-none text-slate-500"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="w-4 h-4"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        <input
          v-model="query"
          type="search"
          placeholder="Search donghua… e.g. Renegade Immortal, Swallowed Star"
          class="w-full pl-10 pr-4 py-3 rounded-md bg-ink-800 text-sm
                 ring-1 ring-white/10 focus:ring-brand-500 focus:bg-ink-800
                 outline-none placeholder:text-slate-500 transition-all"
        />
      </div>
      <div
        v-if="showingSearch && searchProvider"
        class="mt-2 text-xs text-slate-500"
      >
        Searched via <span class="text-slate-300">{{ searchProvider }}</span>
      </div>
    </div>

    <h2 class="text-lg font-semibold mb-4">
      {{ showingSearch ? 'Search Results' : 'Featured' }}
    </h2>

    <div
      v-if="loading && !cards.length"
      class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
    >
      <div
        v-for="i in 10"
        :key="i"
        class="aspect-[2/3] rounded-lg bg-white/5 animate-pulse"
      />
    </div>
    <div
      v-else-if="!cards.length"
      class="text-slate-400 py-12 text-center"
    >
      {{ showingSearch ? `No results for "${debounced}".` : 'Nothing to show.' }}
    </div>
    <div
      v-else
      class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
    >
      <NuxtLink
        v-for="c in cards"
        :key="`${c.provider}:${c.id}`"
        :to="cardLink(c)"
        class="block group"
      >
        <div class="card aspect-[2/3] relative rounded-lg overflow-hidden bg-ink-800">
          <img
            v-if="c.image"
            :src="c.image"
            :alt="c.title"
            loading="lazy"
            class="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
          <div
            v-else
            class="absolute inset-0 flex items-center justify-center text-slate-600 text-3xl"
          >
            🐲
          </div>
          <div
            v-if="c.type"
            class="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-black/60 text-[10px] uppercase tracking-widest text-slate-200"
          >
            {{ c.type }}
          </div>
        </div>
        <div class="mt-2 text-sm font-medium truncate">{{ c.title }}</div>
        <div
          v-if="c.releaseDate"
          class="text-xs text-slate-500 truncate"
        >
          {{ c.releaseDate }}
        </div>
      </NuxtLink>
    </div>
  </div>
</template>
