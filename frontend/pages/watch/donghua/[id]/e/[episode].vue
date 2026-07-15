<script setup lang="ts">
import {
  donghuaInfo,
  donghuaStream,
  donghuaTitle,
  type DonghuaInfo,
} from '~/composables/useDonghua'
import type { StreamResolveResponse } from '~/composables/useStream'

const route = useRoute()
const router = useRouter()

const id = computed(() => String(route.params.id || ''))
const episodeNum = computed(() => Number(route.params.episode))
const provider = computed<'zoro' | 'animekai'>(() =>
  (route.query.provider as 'zoro' | 'animekai') || 'zoro',
)

// `ep` (the provider-scoped episode id) rides on the query string so we
// don't have to re-fetch info just to look it up. Info still loads for the
// title, episode list (Next button), and poster.
const epQuery = computed(() => String(route.query.ep || ''))

const info = ref<DonghuaInfo | null>(null)
const infoPending = ref(true)
onMounted(async () => {
  try {
    info.value = await donghuaInfo(id.value, provider.value)
  } finally {
    infoPending.value = false
  }
})

useHead({
  title: () =>
    `${info.value ? donghuaTitle(info.value.title) : 'Donghua'} · E${episodeNum.value} — Reelhouse`,
})

// Fallback if `ep` isn't in the URL: look it up on the loaded info by number.
const resolvedEpId = computed(() => {
  if (epQuery.value) return epQuery.value
  const list = info.value?.episodes ?? []
  return list.find((e) => e.number === episodeNum.value)?.id ?? ''
})

const resolved = ref<StreamResolveResponse | null>(null)
const pending = ref(true)
const error = ref<unknown>(null)

const fetchStream = async () => {
  if (!resolvedEpId.value) {
    // Info hasn't loaded yet — wait for it to resolve the ep id.
    return
  }
  pending.value = true
  error.value = null
  try {
    resolved.value = await donghuaStream(resolvedEpId.value, provider.value)
  } catch (e) {
    error.value = e
  } finally {
    pending.value = false
  }
}
watch(resolvedEpId, fetchStream, { immediate: true })

const next = computed(() => {
  const list = info.value?.episodes ?? []
  const idx = list.findIndex((e) => e.number === episodeNum.value)
  if (idx < 0 || idx + 1 >= list.length) return undefined
  return list[idx + 1]
})

const contentTitle = computed(() =>
  info.value ? donghuaTitle(info.value.title) : 'Donghua',
)
const contentPoster = computed(() => info.value?.image ?? info.value?.cover ?? null)

// The Player expects a numeric content id (for Continue Watching bookkeeping).
// Same string→int hash as the detail page so the two agree on identity.
const numericId = computed(() => {
  const s = `${provider.value}:${id.value}`
  let n = 0
  for (let i = 0; i < s.length; i++) n = (n * 31 + s.charCodeAt(i)) | 0
  return Math.abs(n)
})

// hianime.ms streams come back as iframe embed URLs (megaplay.buzz +
// vidnest.fun), not raw HLS — so we render an <iframe> instead of the
// video.js Player. `qualities[].url` carries the backup server, which the
// viewer can flip to via the picker.
const isIframe = computed(() => resolved.value?.stream_format === 'iframe')
const iframeSources = computed(() =>
  (resolved.value?.qualities ?? []).filter((q) => q.format === 'iframe'),
)
const activeIframeUrl = ref<string | null>(null)
watch(
  resolved,
  (r) => {
    if (!r) {
      activeIframeUrl.value = null
      return
    }
    if (r.stream_format === 'iframe') {
      activeIframeUrl.value = r.stream_url
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="min-h-screen bg-black">
    <header class="px-4 sm:px-6 py-3 flex items-center gap-3">
      <button class="btn-ghost" @click="router.back()">← Back</button>
      <div class="font-medium truncate">
        {{ contentTitle }}
        <span class="text-slate-400 text-sm ml-2">E{{ episodeNum }}</span>
      </div>
    </header>

    <div class="max-w-6xl mx-auto px-2 sm:px-4">
      <!-- Iframe-embed player (hianime.ms via megaplay/vidnest) -->
      <template v-if="isIframe">
        <div v-if="pending || infoPending" class="aspect-video w-full bg-white/5 flex items-center justify-center rounded">
          <span class="text-slate-500 text-sm">Loading stream…</span>
        </div>
        <div v-else-if="!activeIframeUrl" class="aspect-video w-full bg-white/5 flex flex-col items-center justify-center rounded gap-3 text-slate-400">
          <span>No stream available.</span>
          <button class="btn-ghost" @click="fetchStream">Retry</button>
        </div>
        <div v-else class="relative aspect-video w-full bg-black rounded overflow-hidden">
          <iframe
            :src="activeIframeUrl"
            allow="autoplay; fullscreen; picture-in-picture"
            allowfullscreen
            referrerpolicy="no-referrer"
            class="absolute inset-0 w-full h-full border-0"
          />
        </div>
        <div v-if="iframeSources.length > 1" class="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span class="text-slate-400 uppercase tracking-widest">Server:</span>
          <button
            v-for="s in iframeSources"
            :key="s.url"
            class="px-2 py-1 rounded ring-1 transition-colors"
            :class="
              activeIframeUrl === s.url
                ? 'bg-brand-600/30 ring-brand-500 text-white'
                : 'bg-ink-800 ring-white/10 text-slate-300 hover:text-white'
            "
            @click="activeIframeUrl = s.url"
          >
            {{ s.server || s.resolution || 'Server' }}
          </button>
        </div>
      </template>

      <!-- Native video player (HLS/MP4/DASH) — unchanged path from MovieBox anime -->
      <Player
        v-else
        :resolved="resolved"
        :pending="pending || infoPending"
        :error="error"
        :content-id="numericId"
        content-type="series"
        :content-title="contentTitle"
        :content-poster="contentPoster"
        :season="1"
        :episode="episodeNum"
      />

      <div class="px-2 py-4 max-w-3xl space-y-3">
        <NuxtLink
          v-if="next"
          :to="{
            path: `/watch/donghua/${encodeURIComponent(id)}/e/${next.number}`,
            query: { provider, ep: next.id },
          }"
          class="btn-primary inline-block"
        >
          Next: E{{ next.number }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
