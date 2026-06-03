<script setup lang="ts">
import {
  animeDetail,
  animeTitle,
  animeSearchTitle,
  type AnilistMediaDetail,
} from '~/composables/useAnilist'
import { useMyList } from '~/composables/useMyList'
import { proxiedUrl, type StreamOption, type StreamResolveResponse } from '~/composables/useStream'
import { useSeriesStructure } from '~/composables/useSeriesStructure'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const anime = ref<AnilistMediaDetail | null>(null)
const animePending = ref(true)
const animeError = ref<unknown>(null)

const loadAnime = async () => {
  animePending.value = true
  animeError.value = null
  try {
    anime.value = await animeDetail(id.value)
  } catch (e) {
    animeError.value = e
  } finally {
    animePending.value = false
  }
}
watch(id, loadAnime, { immediate: true })

useHead({
  title: () => `${anime.value ? animeTitle(anime.value.title) : 'Anime'} — Reelhouse`,
})

const myList = useMyList()
const inList = computed(() =>
  anime.value ? myList.has(anime.value.id, 'series') : false,
)
const toggleList = () => {
  if (!anime.value) return
  myList.toggle({
    id: anime.value.id,
    type: 'series',
    title: animeTitle(anime.value.title),
    poster: anime.value.coverImage.large || null,
    year: anime.value.seasonYear ?? null,
  })
}

// Episode picker — restored from URL `?e=` like series page.
const totalEpisodes = computed(() => anime.value?.episodes ?? 0)
const initialEpisode = (() => {
  const v = Number(route.query.e)
  return Number.isFinite(v) && v > 0 ? v : 1
})()
const activeEpisode = ref<number>(initialEpisode)

watch(activeEpisode, (e) => {
  const eStr = String(e)
  if (route.query.e === eStr) return
  router.replace({ path: route.path, query: { ...route.query, e: eStr } })
})

// MovieBox's authoritative structure (via AniList id). The anime page keeps a
// single linear episode index in its URL; we flatten MovieBox's seasons into
// that same 1..N index and map each back to a MovieBox (se, ep) so multi-season
// anime (which AniList numbers linearly) resolve the right file.
const { data: structure } = useSeriesStructure(
  () => (anime.value ? animeSearchTitle(anime.value.title) : ''),
  {
    anilistId: () => anime.value?.id,
    year: () => anime.value?.seasonYear ?? undefined,
  },
)
const flatEpisodes = computed<{ index: number; se: number; ep: number }[]>(() => {
  const s = structure.value
  if (!s) return []
  const out: { index: number; se: number; ep: number }[] = []
  let i = 0
  for (const season of [...s.seasons].sort((a, b) => a.se - b.se)) {
    for (const e of season.episodes) {
      i += 1
      out.push({ index: i, se: season.se, ep: e.ep })
    }
  }
  return out
})
const useStructure = computed(() => flatEpisodes.value.length > 0)
const currentMb = computed(() => flatEpisodes.value.find((e) => e.index === activeEpisode.value))

const episodeOptions = computed<number[]>(() => {
  if (useStructure.value) return flatEpisodes.value.map((e) => e.index)
  const n = totalEpisodes.value
  if (!n) return []
  return Array.from({ length: n }, (_, i) => i + 1)
})

// Stream resolution via existing /api/stream/series — we just feed AniList's
// English title and seasonYear instead of TMDB's.
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

const hasStreams = computed(() => streamQualities.value.length > 0)
const hasDownloads = computed(() => downloadQualities.value.length > 0)

const formatBytes = (n: number) => {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`
  return `${(n / 1e3).toFixed(0)} KB`
}

let availToken = 0
const fetchAvailability = async () => {
  if (!anime.value) return
  availability.value = 'loading'
  const t = ++availToken
  try {
    // Prefer MovieBox's own (se, ep) for this linear index; fall back to the
    // legacy season=1 + linear episode (the backend remap may still bridge it)
    // when the structure isn't available.
    const params = new URLSearchParams({
      anilist_id: String(anime.value.id),
      title: animeSearchTitle(anime.value.title),
      season: String(currentMb.value?.se ?? 1),
      episode: String(currentMb.value?.ep ?? activeEpisode.value),
    })
    if (anime.value.seasonYear) params.set('year', String(anime.value.seasonYear))
    const res = await $fetch<StreamResolveResponse>(
      `${apiBase}/api/stream/series?${params.toString()}`,
    )
    if (t !== availToken) return
    streamQualities.value = res.qualities ?? []
    downloadQualities.value = res.download_qualities ?? []
    playReferer.value = res.play_referer
    availability.value = hasStreams.value || hasDownloads.value ? 'ok' : 'none'
  } catch (e: any) {
    if (t !== availToken) return
    const status = e?.response?.status ?? e?.statusCode
    streamQualities.value = []
    downloadQualities.value = []
    availability.value = status === 404 ? 'none' : 'error'
  }
}

watch(
  [() => anime.value?.id, activeEpisode, () => currentMb.value?.se, () => currentMb.value?.ep],
  ([aid]) => {
    pickerOpen.value = false
    playPickerOpen.value = false
    if (aid) fetchAvailability()
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
  if (!anime.value) return
  playPickerOpen.value = false
  router.push(
    `/watch/anime/${anime.value.id}/e/${activeEpisode.value}` +
      `?q=${encodeURIComponent(opt.resolution)}`,
  )
}

const downloadOption = (opt: StreamOption) => {
  if (!anime.value) return
  const safe = animeTitle(anime.value.title).replace(/[\\/:*?"<>|]+/g, ' ').trim()
  const filename = `${safe} E${String(activeEpisode.value).padStart(2, '0')}.mp4`
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

// Strip HTML tags from AniList description (it may contain <br>, <i>, etc.).
const cleanDescription = computed(() => {
  if (!anime.value?.description) return ''
  return anime.value.description.replace(/<[^>]+>/g, '').trim()
})
</script>

<template>
  <div>
    <div v-if="animePending && !anime" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">Loading…</div>
    <div v-else-if="animeError || !anime" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">Anime not found.</div>
    <template v-else>
      <section class="relative">
        <div class="absolute inset-0 -z-10">
          <img
            v-if="anime.bannerImage"
            :src="anime.bannerImage"
            :alt="animeTitle(anime.title)"
            class="w-full h-full object-cover opacity-50"
          />
          <div class="absolute inset-0 bg-hero-fade" />
        </div>
        <div class="max-w-7xl mx-auto px-6 py-10 grid md:grid-cols-[260px,1fr] gap-8">
          <div class="aspect-[2/3] rounded-lg overflow-hidden bg-ink-800 max-w-[260px]">
            <img
              v-if="anime.coverImage.large || anime.coverImage.extraLarge"
              :src="anime.coverImage.extraLarge || anime.coverImage.large || ''"
              :alt="animeTitle(anime.title)"
              class="w-full h-full object-cover"
            />
          </div>
          <div class="space-y-4">
            <h1 class="text-3xl md:text-4xl font-bold tracking-tight">
              {{ animeTitle(anime.title) }}
            </h1>
            <p
              v-if="anime.title.native && anime.title.english"
              class="italic text-slate-400"
            >
              {{ anime.title.native }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span
                v-if="anime.averageScore"
                class="chip text-accent-gold"
              >★ {{ (anime.averageScore / 10).toFixed(1) }}</span>
              <span v-if="anime.seasonYear" class="chip">{{ anime.seasonYear }}</span>
              <span v-if="anime.format" class="chip">{{ anime.format }}</span>
              <span v-if="anime.episodes" class="chip">{{ anime.episodes }} ep</span>
              <span v-if="anime.status" class="chip">{{ anime.status }}</span>
              <span v-for="g in anime.genres ?? []" :key="g" class="chip">{{ g }}</span>
            </div>
            <p v-if="cleanDescription" class="text-slate-300 max-w-3xl">{{ cleanDescription }}</p>
            <div
              v-if="anime.studios?.nodes?.length"
              class="text-sm text-slate-400"
            >
              Studio:
              <span class="text-slate-200">
                {{ anime.studios.nodes.map((s) => s.name).join(', ') }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-3 pt-2">
              <select
                v-if="episodeOptions.length"
                v-model.number="activeEpisode"
                class="rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm h-[42px]"
              >
                <option v-for="n in episodeOptions" :key="n" :value="n">
                  Episode {{ n }}
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
    </template>
  </div>
</template>
