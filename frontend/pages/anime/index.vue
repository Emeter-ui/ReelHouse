<script setup lang="ts">
import {
  browseAnime,
  recentAnime,
  animeTitle,
  type AnilistMediaSummary,
} from '~/composables/useAnilist'

useHead({ title: 'Anime — Reelhouse' })

const filters = ref<{
  year?: number | ''
  sort: string
}>({ year: '', sort: 'POPULARITY_DESC' })
const page = ref(1)
watch(filters, () => (page.value = 1), { deep: true })

const sorts = [
  { v: 'POPULARITY_DESC', label: 'Popular' },
  { v: 'SCORE_DESC', label: 'Top Rated' },
  { v: 'START_DATE_DESC', label: 'Newest' },
  { v: 'TRENDING_DESC', label: 'Trending' },
]

const thisYear = new Date().getFullYear()
const years = Array.from({ length: 60 }, (_, i) => thisYear - i)

// Recent (just-aired) row — not paginated.
const recent = ref<AnilistMediaSummary[] | null>(null)
const recentLoading = ref(true)
onMounted(async () => {
  try {
    recent.value = await recentAnime(20)
  } finally {
    recentLoading.value = false
  }
})

// Discover grid — refetches on filter or page change.
const discover = ref<{
  media: AnilistMediaSummary[]
  pageInfo: { currentPage: number; lastPage: number; hasNextPage: boolean }
} | null>(null)
const discoverLoading = ref(false)
let token = 0
const fetchDiscover = async () => {
  discoverLoading.value = true
  const t = ++token
  try {
    const res = await browseAnime({
      page: page.value,
      perPage: 20,
      sort: [filters.value.sort],
      year: filters.value.year || undefined,
    })
    if (t !== token) return
    discover.value = res
  } finally {
    if (t === token) discoverLoading.value = false
  }
}
watch([filters, page], fetchDiscover, { immediate: true, deep: true })

// Recent-row scroll arrows.
const recentRow = ref<HTMLDivElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(true)
const updateScrollState = () => {
  const el = recentRow.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 4
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 4
}
const scrollRow = (dir: 'left' | 'right') => {
  const el = recentRow.value
  if (!el) return
  const delta = el.clientWidth * 0.85
  el.scrollBy({ left: dir === 'left' ? -delta : delta, behavior: 'smooth' })
}
onMounted(() => {
  updateScrollState()
  window.addEventListener('resize', updateScrollState)
})
onBeforeUnmount(() => window.removeEventListener('resize', updateScrollState))
watch(recent, () => nextTick(updateScrollState))
</script>

<template>
  <div class="pb-16">
    <!-- Recent anime row -->
    <section class="my-8 max-w-7xl mx-auto">
      <div class="px-6 mb-4">
        <h2 class="text-xl font-bold tracking-tight text-white/90">Recent Anime</h2>
        <p class="text-sm text-slate-400">Latest aired — fresh off the schedule.</p>
      </div>

      <div v-if="recentLoading" class="row-scroll px-6">
        <div
          v-for="i in 8"
          :key="i"
          class="w-36 sm:w-48 md:w-52 aspect-[2/3] rounded-xl bg-white/5 animate-pulse shrink-0"
        />
      </div>
      <div
        v-else-if="!recent?.length"
        class="px-6 text-sm text-slate-500 py-10 text-center"
      >
        Nothing recent.
      </div>
      <div v-else class="relative group">
        <div
          ref="recentRow"
          class="row-scroll px-6 mask-fade"
          @scroll="updateScrollState"
        >
          <MovieCard
            v-for="a in recent"
            :key="a.id"
            :id="a.id"
            type="anime"
            :title="animeTitle(a.title)"
            :poster="a.coverImage.large || a.coverImage.medium || null"
            :year="a.seasonYear ?? null"
            :rating="a.averageScore != null ? a.averageScore / 10 : null"
          />
          <div class="w-1 shrink-0" />
        </div>

        <button
          v-show="canScrollLeft"
          type="button"
          aria-label="Scroll left"
          class="hidden md:flex absolute left-2 top-1/2 -translate-y-1/2 z-10
                 w-10 h-10 items-center justify-center rounded-full
                 bg-black/60 hover:bg-black/80 text-white text-xl
                 ring-1 ring-white/10 backdrop-blur-md
                 opacity-0 group-hover:opacity-100 transition"
          @click="scrollRow('left')"
        >
          ‹
        </button>
        <button
          v-show="canScrollRight"
          type="button"
          aria-label="Scroll right"
          class="hidden md:flex absolute right-2 top-1/2 -translate-y-1/2 z-10
                 w-10 h-10 items-center justify-center rounded-full
                 bg-black/60 hover:bg-black/80 text-white text-xl
                 ring-1 ring-white/10 backdrop-blur-md
                 opacity-0 group-hover:opacity-100 transition"
          @click="scrollRow('right')"
        >
          ›
        </button>
      </div>
    </section>

    <!-- Discover grid -->
    <div class="max-w-7xl mx-auto px-6">
      <h1 class="text-2xl font-bold mb-6">Anime</h1>

      <div class="flex flex-col md:flex-row gap-8">
        <aside class="w-full md:w-64 shrink-0 space-y-6">
          <div>
            <div class="text-xs uppercase tracking-wider text-slate-400 mb-2">Year</div>
            <select
              v-model.number="filters.year"
              class="w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
            >
              <option value="">Any year</option>
              <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>

          <div>
            <div class="text-xs uppercase tracking-wider text-slate-400 mb-2">Sort</div>
            <select
              v-model="filters.sort"
              class="w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
            >
              <option v-for="s in sorts" :key="s.v" :value="s.v">{{ s.label }}</option>
            </select>
          </div>

          <button
            class="btn-ghost w-full justify-center"
            @click="filters = { year: '', sort: 'POPULARITY_DESC' }"
          >
            Reset filters
          </button>
        </aside>

        <div class="flex-1 min-w-0">
          <div
            v-if="discoverLoading && !discover"
            class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
          >
            <div
              v-for="i in 15"
              :key="i"
              class="aspect-[2/3] rounded-lg bg-white/5 animate-pulse"
            />
          </div>
          <div
            v-else-if="!discover?.media?.length"
            class="text-slate-400 py-12 text-center"
          >
            No anime match your filters.
          </div>
          <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <MovieCard
              v-for="a in discover.media"
              :key="a.id"
              :id="a.id"
              type="anime"
              :title="animeTitle(a.title)"
              :poster="a.coverImage.large || a.coverImage.medium || null"
              :year="a.seasonYear ?? null"
              :rating="a.averageScore != null ? a.averageScore / 10 : null"
              size="full"
            />
          </div>

          <div
            v-if="discover && discover.pageInfo.lastPage > 1"
            class="flex items-center justify-center gap-3 mt-8"
          >
            <button
              class="btn-ghost disabled:opacity-30"
              :disabled="page <= 1"
              @click="page = Math.max(1, page - 1)"
            >
              Prev
            </button>
            <span class="text-sm text-slate-400">
              Page {{ discover.pageInfo.currentPage }} of {{ discover.pageInfo.lastPage }}
            </span>
            <button
              class="btn-ghost disabled:opacity-30"
              :disabled="!discover.pageInfo.hasNextPage"
              @click="page = page + 1"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask-fade {
  mask-image: linear-gradient(to right, transparent, black 40px, black calc(100% - 40px), transparent);
}
@media (max-width: 640px) {
  .mask-fade {
    mask-image: none;
  }
}
</style>
