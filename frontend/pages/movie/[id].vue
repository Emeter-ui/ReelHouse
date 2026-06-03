<script setup lang="ts">
import { useTmdb, tmdbImg } from '~/composables/useTmdb'
import { useMyList } from '~/composables/useMyList'
import { proxiedUrl, type StreamOption, type StreamResolveResponse } from '~/composables/useStream'
const route = useRoute()
const id = computed(() => Number(route.params.id))

type Cast = { id: number; name: string; character: string; profile_path: string | null }
type Crew = { id: number; name: string; job: string }
type Movie = {
  id: number
  title: string
  tagline: string
  overview: string
  poster_path: string | null
  backdrop_path: string | null
  release_date: string
  runtime: number
  vote_average: number
  genres: { id: number; name: string }[]
  credits?: { cast: Cast[]; crew: Crew[] }
  similar?: { results: Array<{ id: number; title: string; poster_path: string | null; release_date?: string; vote_average?: number }> }
}

const { data: movie, pending, error } = useTmdb<Movie>(
  () => `movie/${id.value}`,
  { append_to_response: 'credits,similar' },
  { lazy: true },
)

useHead({ title: () => `${movie.value?.title ?? 'Movie'} — Reelhouse` })

const myList = useMyList()
const inList = computed(() =>
  movie.value ? myList.has(movie.value.id, 'movie') : false,
)
const toggleList = () => {
  if (!movie.value) return
  myList.toggle({
    id: movie.value.id,
    type: 'movie',
    title: movie.value.title,
    poster: movie.value.poster_path,
    year: movie.value.release_date ? Number(movie.value.release_date.slice(0, 4)) : null,
  })
}

const director = computed(() =>
  movie.value?.credits?.crew?.find((c) => c.job === 'Director')?.name,
)
const cast = computed(() => movie.value?.credits?.cast?.slice(0, 8) ?? [])
const similar = computed(() => movie.value?.similar?.results?.slice(0, 12) ?? [])

const runtime = computed(() => {
  const r = movie.value?.runtime
  if (!r) return ''
  const h = Math.floor(r / 60)
  const m = r % 60
  return h ? `${h}h ${m}m` : `${m}m`
})

const year = computed(() =>
  movie.value?.release_date ? movie.value.release_date.slice(0, 4) : '',
)

const { public: { apiBase } } = useRuntimeConfig()
const pickerOpen = ref(false)
const playPickerOpen = ref(false)
const streamQualities = ref<StreamOption[]>([])
const downloadQualities = ref<StreamOption[]>([])
const playReferer = ref<string | undefined>(undefined)
const availability = ref<'loading' | 'ok' | 'none' | 'error'>('loading')
const downloadButton = ref<HTMLButtonElement | null>(null)
const pickerEl = ref<HTMLDivElement | null>(null)
const playButton = ref<HTMLButtonElement | null>(null)
const playPickerEl = ref<HTMLDivElement | null>(null)
const router = useRouter()

const hasStreams = computed(() => streamQualities.value.length > 0)
const hasDownloads = computed(() => downloadQualities.value.length > 0)

const formatBytes = (n: number) => {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`
  return `${(n / 1e3).toFixed(0)} KB`
}

const fetchAvailability = async () => {
  if (!movie.value) return
  availability.value = 'loading'
  try {
    const params = new URLSearchParams({
      tmdb_id: String(movie.value.id),
      title: movie.value.title,
    })
    if (year.value) params.set('year', year.value)
    const res = await $fetch<StreamResolveResponse>(
      `${apiBase}/api/stream/movie?${params.toString()}`,
    )
    streamQualities.value = res.qualities ?? []
    downloadQualities.value = res.download_qualities ?? []
    playReferer.value = res.play_referer
    availability.value = hasStreams.value || hasDownloads.value ? 'ok' : 'none'
  } catch (e: any) {
    const status = e?.response?.status ?? e?.statusCode
    streamQualities.value = []
    downloadQualities.value = []
    // 404 is "MovieBox has nothing for this title" — coming soon.
    availability.value = status === 404 ? 'none' : 'error'
  }
}

// Auto-fetch as soon as we know the movie title.
watch(
  () => movie.value?.id,
  (id) => {
    if (id) fetchAvailability()
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
  if (!movie.value) return
  playPickerOpen.value = false
  router.push(`/watch/movie/${movie.value.id}?q=${encodeURIComponent(opt.resolution)}`)
}

const downloadOption = (opt: StreamOption) => {
  if (!movie.value) return
  const safe = movie.value.title.replace(/[\\/:*?"<>|]+/g, ' ').trim()
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
    <div v-if="pending && !movie" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">Loading…</div>
    <div v-else-if="error || !movie" class="max-w-7xl mx-auto px-6 py-16 text-slate-400">
      Movie not found.
    </div>
    <template v-else>
      <section class="relative">
        <div class="absolute inset-0 -z-10">
          <img
            v-if="movie.backdrop_path"
            :src="tmdbImg(movie.backdrop_path, 'original')"
            :alt="movie.title"
            class="w-full h-full object-cover opacity-50"
          />
          <div class="absolute inset-0 bg-hero-fade" />
        </div>
        <div class="max-w-7xl mx-auto px-6 py-10 grid md:grid-cols-[260px,1fr] gap-8">
          <div class="aspect-[2/3] rounded-lg overflow-hidden bg-ink-800 max-w-[260px]">
            <img
              v-if="movie.poster_path"
              :src="tmdbImg(movie.poster_path, 'w500')"
              :alt="movie.title"
              class="w-full h-full object-cover"
            />
          </div>
          <div class="space-y-4">
            <h1 class="text-3xl md:text-4xl font-bold tracking-tight">{{ movie.title }}</h1>
            <p v-if="movie.tagline" class="italic text-slate-400">{{ movie.tagline }}</p>
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span v-if="movie.vote_average" class="chip text-accent-gold">★ {{ movie.vote_average.toFixed(1) }}</span>
              <span v-if="year" class="chip">{{ year }}</span>
              <span v-if="runtime" class="chip">{{ runtime }}</span>
              <span v-for="g in movie.genres" :key="g.id" class="chip">{{ g.name }}</span>
            </div>
            <p class="text-slate-300 max-w-3xl">{{ movie.overview }}</p>
            <div v-if="director" class="text-sm text-slate-400">Directed by <span class="text-slate-200">{{ director }}</span></div>
            <div class="flex flex-wrap gap-3 pt-2">
              <div class="relative">
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
                    v-if="availability === 'loading'"
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
              <div class="relative">
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
                    v-if="availability === 'loading'"
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
              <button class="btn-ghost" @click="toggleList">
                {{ inList ? '✓ In My List' : '+ My List' }}
              </button>
            </div>
          </div>
        </div>
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
            v-for="m in similar"
            :key="m.id"
            :id="m.id"
            type="movie"
            :title="m.title"
            :poster="m.poster_path"
            :year="m.release_date ? Number(m.release_date.slice(0, 4)) : null"
            :rating="m.vote_average ?? null"
            size="sm"
          />
        </div>
      </section>
    </template>
  </div>
</template>
