<script setup lang="ts">
import { donghuaInfo, donghuaTitle, type DonghuaInfo } from '~/composables/useDonghua'
import { useMyList } from '~/composables/useMyList'

const route = useRoute()
const router = useRouter()

const id = computed(() => String(route.params.id || ''))
const provider = computed<'zoro' | 'animekai'>(() =>
  (route.query.provider as 'zoro' | 'animekai') || 'zoro',
)

const info = ref<DonghuaInfo | null>(null)
const pending = ref(true)
const error = ref<unknown>(null)

const loadInfo = async () => {
  pending.value = true
  error.value = null
  try {
    info.value = await donghuaInfo(id.value, provider.value)
  } catch (e) {
    error.value = e
  } finally {
    pending.value = false
  }
}
watch([id, provider], loadInfo, { immediate: true })

useHead({
  title: () =>
    `${info.value ? donghuaTitle(info.value.title) : 'Donghua'} — Reelhouse`,
})

const title = computed(() =>
  info.value ? donghuaTitle(info.value.title) : 'Loading…',
)
const poster = computed(() => info.value?.image ?? info.value?.cover ?? null)
const banner = computed(() => info.value?.cover ?? info.value?.image ?? null)

// Numeric ids only in myList — donghua ids are strings, so we hash to a stable
// int by taking the sum of char codes (collision-tolerant for personal use).
const numericId = computed(() => {
  const s = `${provider.value}:${id.value}`
  let n = 0
  for (let i = 0; i < s.length; i++) n = (n * 31 + s.charCodeAt(i)) | 0
  return Math.abs(n)
})

const myList = useMyList()
const inList = computed(() => myList.has(numericId.value, 'series'))
const toggleList = () => {
  if (!info.value) return
  myList.toggle({
    id: numericId.value,
    type: 'series',
    title: donghuaTitle(info.value.title),
    poster: poster.value,
    year: info.value.releaseDate ? Number(info.value.releaseDate.slice(0, 4)) : null,
  })
}

const episodes = computed(() => info.value?.episodes ?? [])

// Episode picker state — track current index, persist to URL like other pages.
const initialEpisode = (() => {
  const v = Number(route.query.e)
  return Number.isFinite(v) && v > 0 ? v : 1
})()
const activeEpisode = ref<number>(initialEpisode)
watch(activeEpisode, (e) => {
  const s = String(e)
  if (route.query.e === s) return
  router.replace({ path: route.path, query: { ...route.query, e: s } })
})

const currentEp = computed(() =>
  episodes.value.find((e) => e.number === activeEpisode.value) ?? episodes.value[0],
)

const play = () => {
  if (!currentEp.value) return
  router.push({
    path: `/watch/donghua/${encodeURIComponent(id.value)}/e/${currentEp.value.number}`,
    query: {
      provider: provider.value,
      ep: currentEp.value.id,
    },
  })
}

const description = computed(() => info.value?.description ?? '')
</script>

<template>
  <div class="pb-16">
    <div
      v-if="pending"
      class="max-w-6xl mx-auto px-4 sm:px-6 pt-8 space-y-6"
    >
      <div class="h-64 rounded-xl bg-white/5 animate-pulse" />
      <div class="h-8 w-1/2 rounded bg-white/5 animate-pulse" />
      <div class="h-4 w-2/3 rounded bg-white/5 animate-pulse" />
    </div>

    <div
      v-else-if="error"
      class="max-w-6xl mx-auto px-4 sm:px-6 pt-8"
    >
      <div class="text-red-400">
        Couldn't load this donghua ({{ String(error) }}).
      </div>
      <button class="btn-ghost mt-4" @click="loadInfo">Retry</button>
    </div>

    <template v-else-if="info">
      <!-- Banner + title -->
      <div class="relative">
        <div
          v-if="banner"
          class="absolute inset-x-0 top-0 h-56 sm:h-72 overflow-hidden"
        >
          <img
            :src="banner"
            :alt="title"
            class="w-full h-full object-cover opacity-30"
          />
          <div
            class="absolute inset-0 bg-gradient-to-b from-transparent via-ink-950/40 to-ink-950"
          />
        </div>

        <div class="relative max-w-6xl mx-auto px-4 sm:px-6 pt-6 sm:pt-10">
          <div class="flex flex-col sm:flex-row gap-6">
            <div class="w-40 sm:w-52 shrink-0">
              <div class="aspect-[2/3] rounded-lg overflow-hidden bg-ink-800">
                <img
                  v-if="poster"
                  :src="poster"
                  :alt="title"
                  class="w-full h-full object-cover"
                />
              </div>
            </div>

            <div class="flex-1 min-w-0">
              <h1 class="text-2xl sm:text-3xl font-bold">{{ title }}</h1>
              <div class="mt-1 text-xs text-slate-400 flex flex-wrap items-center gap-2">
                <span
                  v-if="info.releaseDate"
                  class="px-1.5 py-0.5 rounded bg-white/5"
                >{{ info.releaseDate }}</span>
                <span
                  v-if="info.status"
                  class="px-1.5 py-0.5 rounded bg-white/5"
                >{{ info.status }}</span>
                <span
                  v-if="info.totalEpisodes"
                  class="px-1.5 py-0.5 rounded bg-white/5"
                >{{ info.totalEpisodes }} eps</span>
                <span class="px-1.5 py-0.5 rounded bg-brand-600/25 text-brand-300">
                  {{ provider }}
                </span>
              </div>

              <p
                v-if="description"
                class="mt-4 text-sm text-slate-300 leading-relaxed line-clamp-5"
              >{{ description }}</p>

              <div class="mt-5 flex flex-wrap items-center gap-3">
                <div class="flex items-center gap-2">
                  <label class="text-xs uppercase tracking-widest text-slate-400">
                    Episode
                  </label>
                  <select
                    v-model.number="activeEpisode"
                    class="rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
                    :disabled="!episodes.length"
                  >
                    <option
                      v-for="e in episodes"
                      :key="e.id"
                      :value="e.number"
                    >
                      E{{ e.number }}{{ e.title ? ` — ${e.title}` : '' }}
                    </option>
                  </select>
                </div>

                <button
                  class="btn-primary"
                  :disabled="!currentEp"
                  @click="play"
                >
                  ▶ Play
                </button>

                <button
                  class="btn-ghost"
                  :aria-pressed="inList"
                  @click="toggleList"
                >
                  {{ inList ? '✓ In My List' : '+ My List' }}
                </button>
              </div>

              <div v-if="!episodes.length" class="mt-4 text-sm text-amber-300/80">
                No episodes reported by this provider.
                <NuxtLink
                  :to="`/donghua/${encodeURIComponent(id)}?provider=${provider === 'zoro' ? 'animekai' : 'zoro'}`"
                  class="underline hover:text-amber-200"
                >
                  Try {{ provider === 'zoro' ? 'AnimeKai' : 'Zoro' }}
                </NuxtLink>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Episode grid -->
      <div v-if="episodes.length" class="max-w-6xl mx-auto px-4 sm:px-6 mt-8">
        <h2 class="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">
          Episodes
        </h2>
        <div
          class="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2"
        >
          <button
            v-for="e in episodes"
            :key="e.id"
            class="px-2 py-2 rounded-md text-sm border transition-colors"
            :class="
              activeEpisode === e.number
                ? 'border-brand-500 bg-brand-600/20 text-white'
                : 'border-white/10 hover:border-white/20 text-slate-300'
            "
            @click="activeEpisode = e.number"
          >
            {{ e.number }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
