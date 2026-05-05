<script setup lang="ts">
import { useTmdb, tmdbImg } from '~/composables/useTmdb'
import { useMyList } from '~/composables/useMyList'
import { proxiedUrl, type StreamOption, type StreamResolveResponse } from '~/composables/useStream'
const route = useRoute()
const id = computed(() => Number(route.params.id))

type Cast = { id: number; name: string; character: string; profile_path: string | null }
type SeasonStub = { id: number; season_number: number; name: string; episode_count: number; air_date: string | null; poster_path: string | null; overview: string }
type Episode = { id: number; episode_number: number; name: string; overview: string; still_path: string | null; air_date: string | null; runtime: number | null; vote_average: number }
type Series = {
  id: number
  name: string
  tagline: string
  overview: string
  poster_path: string | null
  backdrop_path: string | null
  first_air_date: string
  number_of_seasons: number
  vote_average: number
  genres: { id: number; name: string }[]
  seasons: SeasonStub[]
  credits?: { cast: Cast[] }
  similar?: { results: Array<{ id: number; name: string; poster_path: string | null; first_air_date?: string; vote_average?: number }> }
}

const { data: series, pending, error } = useTmdb<Series>(
  () => `tv/${id.value}`,
  { append_to_response: 'credits,similar' },
  { lazy: true },
)

useHead({ title: () => `${series.value?.name ?? 'Series'} — Reelhouse` })

const myList = useMyList()
const inList = computed(() => (series.value ? myList.has(series.value.id, 'series') : false))
const toggleList = () => {
  if (!series.value) return
  myList.toggle({
    id: series.value.id,
    type: 'series',
    title: series.value.name,
    poster: series.value.poster_path,
    year: series.value.first_air_date ? Number(series.value.first_air_date.slice(0, 4)) : null,
  })
}

const seasons = computed<SeasonStub[]>(() =>
  (series.value?.seasons ?? []).filter((s) => s.season_number > 0),
)

// Persist season/episode in the URL so back-navigation from /watch
// restores what the user was browsing.
const initialSeason = (() => {
  const v = Number(route.query.s)
  return Number.isFinite(v) && v > 0 ? v : null
})()
const initialEpisode = (() => {
  const v = Number(route.query.e)
  return Number.isFinite(v) && v > 0 ? v : 1
})()

const activeSeason = ref<number | null>(initialSeason)
const activeEpisode = ref<number>(initialEpisode)

watch(seasons, (s) => {
  if (s.length && activeSeason.value === null) activeSeason.value = s[0].season_number
})

// User-driven season change resets episode; programmatic changes (URL restore,
// auto-default) leave episode alone.
const onSeasonPicked = (n: number) => {
  if (n === activeSeason.value) return
  activeSeason.value = n
  activeEpisode.value = 1
}

const { data: seasonData, pending: seasonPending } = await useTmdb<{ episodes: Episode[] }>(
  () => `tv/${id.value}/season/${activeSeason.value ?? 1}`,
  {},
  { lazy: true },
)

const episodes = computed<Episode[]>(() => seasonData.value?.episodes ?? [])
watch(episodes, (eps) => {
  if (eps.length && !eps.some((e) => e.episode_number === activeEpisode.value)) {
    activeEpisode.value = eps[0].episode_number
  }
})

const cast = computed(() => series.value?.credits?.cast?.slice(0, 8) ?? [])
const similar = computed(() => series.value?.similar?.results?.slice(0, 12) ?? [])
const year = computed(() =>
  series.value?.first_air_date ? series.value.first_air_date.slice(0, 4) : '',
)

const { public: { apiBase } } = useRuntimeConfig()
const pickerOpen = ref(false)
const playPickerOpen = ref(false)
const streamQualities = ref<StreamOption[]>([])
const downloadQualities = ref<StreamOption[]>([])
const playReferer = ref<string | undefined>(undefined)
const availability = ref<'idle' | 'loading' | 'ok' | 'none' | 'error'>('idle')
const downloadButton = ref<HTMLButtonElement | null>(null)
const pickerEl = ref<HTMLDivElement | null>(null)
const playButton = ref<HTMLButtonElement | null>(null)
const playPickerEl = ref<HTMLDivElement | null>(null)
const router = useRouter()

const hasStreams = computed(() => streamQualities.value.length > 0)
const hasDownloads = computed(() => downloadQualities.value.length > 0)

// Mirror season/episode into the URL (replace, don't push, so we don't
// pollute history). Skips when values match — avoids extra navigations.
watch([activeSeason, activeEpisode], ([s, e]) => {
  if (s === null) return
  const sStr = String(s)
  const eStr = String(e)
  if (route.query.s === sStr && route.query.e === eStr) return
  router.replace({ path: route.path, query: { ...route.query, s: sStr, e: eStr } })
})

const formatBytes = (n: number) => {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`
  return `${(n / 1e3).toFixed(0)} KB`
}

let availabilityToken = 0
const fetchAvailability = async () => {
  if (!series.value || activeSeason.value === null || activeEpisode.value === null) return
  availability.value = 'loading'
  const token = ++availabilityToken
  try {
    const params = new URLSearchParams({
      tmdb_id: String(series.value.id),
      title: series.value.name,
      season: String(activeSeason.value),
      episode: String(activeEpisode.value),
    })
    if (year.value) params.set('year', year.value)
    const res = await $fetch<StreamResolveResponse>(
      `${apiBase}/api/stream/series?${params.toString()}`,
    )
    // Drop late responses for stale episodes
    if (token !== availabilityToken) return
    streamQualities.value = res.qualities ?? []
    downloadQualities.value = res.download_qualities ?? []
    playReferer.value = res.play_referer
    availability.value = hasStreams.value || hasDownloads.value ? 'ok' : 'none'
  } catch (e: any) {
    if (token !== availabilityToken) return
    const status = e?.response?.status ?? e?.statusCode
    streamQualities.value = []
    downloadQualities.value = []
    availability.value = status === 404 ? 'none' : 'error'
  }
}

// Refetch when the user picks a different season/episode (or on first load).
watch(
  [() => series.value?.id, activeSeason, activeEpisode],
  ([id, s, e]) => {
    pickerOpen.value = false
    playPickerOpen.value = false
    if (id && s !== null && e !== null) fetchAvailability()
  },
  { immediate: true },
)

const togglePicker = () => {
  pickerOpen.value = !pickerOpen.value
  if (pickerOpen.value) playPickerOpen.value = false
}

const togglePlayPicker = () => {
  playPickerOpen.value = !playPickerOpen.value
  if (playPickerOpen.value) pickerOpen.value = false
}

const playOption = (opt: StreamOption) => {
  if (!series.value || activeSeason.value === null) return
  playPickerOpen.value = false
  router.push(
    `/watch/series/${series.value.id}/s/${activeSeason.value}/e/${activeEpisode.value}` +
      `?q=${encodeURIComponent(opt.resolution)}`,
  )
}

const downloadOption = (opt: StreamOption) => {
  if (!series.value) return
  const safe = `${series.value.name} S${activeSeason.value}E${activeEpisode.value}`.replace(/[\\/:*?"<>|]+/g, ' ').trim()
  const filename = `${safe}.mp4`
  const a = document.createElement('a')
  a.href = proxiedUrl(opt.url, playReferer.value, filename)
  a.download = filename
  a.target = '_blank'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  pickerOpen.value = false
}

const onDocClick = (e: MouseEvent) => {
  const t = e.target as Node
  if (pickerOpen.value && !pickerEl.value?.contains(t) && !downloadButton.value?.contains(t)) {
    pickerOpen.value = false
  }
  if (playPickerOpen.value && !playPickerEl.value?.contains(t) && !playButton.value?.contains(t)) {
    playPickerOpen.value = false
  }
}
const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    pickerOpen.value = false
    playPickerOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div>
    <div v-if="pending && !series" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">Loading…</div>
    <div v-else-if="error || !series" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">Series not found.</div>
    <template v-else>
      <section class="relative">
        <div class="absolute inset-0 -z-10">
          <img
            v-if="series.backdrop_path"
            :src="tmdbImg(series.backdrop_path, 'original')"
            :alt="series.name"
            class="w-full h-full object-cover opacity-50"
          />
          <div class="absolute inset-0 bg-hero-fade" />
        </div>
        <div class="max-w-7xl mx-auto px-6 py-10 grid md:grid-cols-[260px,1fr] gap-8">
          <div class="aspect-[2/3] rounded-lg overflow-hidden bg-ink-800 max-w-[260px]">
            <img
              v-if="series.poster_path"
              :src="tmdbImg(series.poster_path, 'w500')"
              :alt="series.name"
              class="w-full h-full object-cover"
            />
          </div>
          <div class="space-y-4">
            <h1 class="text-3xl md:text-4xl font-bold tracking-tight">{{ series.name }}</h1>
            <p v-if="series.tagline" class="italic text-slate-400">{{ series.tagline }}</p>
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span v-if="series.vote_average" class="chip text-accent-gold">★ {{ series.vote_average.toFixed(1) }}</span>
              <span v-if="year" class="chip">{{ year }}</span>
              <span v-if="series.number_of_seasons" class="chip">{{ series.number_of_seasons }} season{{ series.number_of_seasons === 1 ? '' : 's' }}</span>
              <span v-for="g in series.genres" :key="g.id" class="chip">{{ g.name }}</span>
            </div>
            <p class="text-slate-300 max-w-3xl">{{ series.overview }}</p>
            <div class="flex flex-wrap items-center gap-3 pt-2">
              <select
                v-if="seasons.length"
                :value="activeSeason"
                class="rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm h-[42px]"
                @change="onSeasonPicked(Number(($event.target as HTMLSelectElement).value))"
              >
                <option v-for="s in seasons" :key="s.id" :value="s.season_number">
                  {{ s.name }} ({{ s.episode_count }} ep)
                </option>
              </select>
              <select
                v-if="episodes.length"
                v-model.number="activeEpisode"
                class="rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm h-[42px]"
              >
                <option v-for="e in episodes" :key="e.id" :value="e.episode_number">
                  E{{ e.episode_number }} — {{ e.name }}
                </option>
              </select>
              <div class="relative shrink-0">
                <button
                  ref="playButton"
                  class="btn-primary"
                  :aria-expanded="playPickerOpen"
                  aria-haspopup="menu"
                  @click="togglePlayPicker"
                >
                  ▶ Play
                </button>
                <div
                  v-if="playPickerOpen"
                  ref="playPickerEl"
                  role="menu"
                  class="absolute z-20 mt-2 left-0 min-w-[14rem] bg-ink-900
                         ring-1 ring-white/10 rounded-lg shadow-xl p-1"
                >
                  <div
                    v-if="availability === 'loading' || availability === 'idle'"
                    class="px-3 py-2 text-sm text-slate-400"
                  >
                    Loading…
                  </div>
                  <div
                    v-else-if="!streamQualities.length"
                    class="px-3 py-2 text-sm text-slate-400"
                  >
                    Not available.
                  </div>
                  <button
                    v-for="q in streamQualities"
                    v-else
                    :key="q.url"
                    role="menuitem"
                    class="w-full flex items-center justify-between gap-4 px-3 py-2
                           rounded-md text-sm hover:bg-white/5"
                    @click="playOption(q)"
                  >
                    <span class="font-medium">{{ q.resolution }}</span>
                    <span class="text-slate-400">{{ formatBytes(q.size_bytes) }}</span>
                  </button>
                </div>
              </div>
              <div class="relative shrink-0">
                <button
                  ref="downloadButton"
                  class="btn-ghost"
                  :aria-expanded="pickerOpen"
                  aria-haspopup="menu"
                  @click="togglePicker"
                >
                  ⬇ Download
                </button>
                <div
                  v-if="pickerOpen"
                  ref="pickerEl"
                  role="menu"
                  class="absolute z-20 mt-2 right-0 min-w-[14rem] bg-ink-900
                         ring-1 ring-white/10 rounded-lg shadow-xl p-1"
                >
                  <div
                    v-if="availability === 'loading' || availability === 'idle'"
                    class="px-3 py-2 text-sm text-slate-400"
                  >
                    Loading…
                  </div>
                  <div
                    v-else-if="!downloadQualities.length"
                    class="px-3 py-2 text-sm text-slate-400"
                  >
                    Not available.
                  </div>
                  <button
                    v-for="q in downloadQualities"
                    v-else
                    :key="q.url"
                    role="menuitem"
                    class="w-full flex items-center justify-between gap-4 px-3 py-2
                           rounded-md text-sm hover:bg-white/5"
                    @click="downloadOption(q)"
                  >
                    <span class="font-medium">{{ q.resolution }}</span>
                    <span class="text-slate-400">{{ formatBytes(q.size_bytes) }}</span>
                  </button>
                </div>
              </div>
              <button class="btn-ghost shrink-0" @click="toggleList">
                {{ inList ? '✓ In My List' : '+ My List' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="max-w-7xl mx-auto px-6 my-8">
        <div class="flex items-center justify-between mb-4 gap-4 flex-wrap">
          <h2 class="text-lg font-semibold">Episodes</h2>
        </div>

        <div v-if="seasonPending && !seasonData" class="text-slate-400 py-8 text-center">Loading episodes…</div>
        <div v-else-if="!seasonData?.episodes?.length" class="text-slate-400 py-8 text-center">No episodes.</div>
        <ul v-else class="divide-y divide-white/5 rounded-lg ring-1 ring-white/5 overflow-hidden">
          <li v-for="e in seasonData.episodes" :key="e.id">
            <NuxtLink
              :to="`/watch/series/${series.id}/s/${activeSeason}/e/${e.episode_number}`"
              class="flex gap-4 p-3 hover:bg-white/5"
            >
              <div class="w-40 aspect-video rounded-md bg-ink-800 overflow-hidden shrink-0">
                <img
                  v-if="e.still_path"
                  :src="tmdbImg(e.still_path, 'w300')"
                  :alt="e.name"
                  class="w-full h-full object-cover"
                />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-baseline gap-2">
                  <span class="text-slate-400 text-sm">E{{ e.episode_number }}</span>
                  <span class="font-medium line-clamp-1">{{ e.name }}</span>
                </div>
                <p class="text-sm text-slate-400 line-clamp-2 mt-1">{{ e.overview }}</p>
                <div class="text-xs text-slate-500 mt-1 flex gap-3">
                  <span v-if="e.air_date">{{ e.air_date }}</span>
                  <span v-if="e.runtime">{{ e.runtime }}m</span>
                </div>
              </div>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <section v-if="cast.length" class="max-w-7xl mx-auto px-6 my-10">
        <h2 class="text-lg font-semibold mb-4">Cast</h2>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-4">
          <div v-for="p in cast" :key="p.id" class="text-center">
            <div class="aspect-square rounded-full overflow-hidden bg-ink-800 mb-2">
              <img
                v-if="p.profile_path"
                :src="tmdbImg(p.profile_path, 'w300')"
                :alt="p.name"
                class="w-full h-full object-cover"
              />
            </div>
            <div class="text-sm font-medium line-clamp-1">{{ p.name }}</div>
            <div class="text-xs text-slate-400 line-clamp-1">{{ p.character }}</div>
          </div>
        </div>
      </section>

      <section v-if="similar.length" class="max-w-7xl mx-auto px-6 my-10">
        <h2 class="text-lg font-semibold mb-4">Similar</h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <MovieCard
            v-for="s in similar"
            :key="s.id"
            :id="s.id"
            type="series"
            :title="s.name"
            :poster="s.poster_path"
            :year="s.first_air_date ? Number(s.first_air_date.slice(0, 4)) : null"
            :rating="s.vote_average ?? null"
            size="full"
          />
        </div>
      </section>
    </template>
  </div>
</template>
