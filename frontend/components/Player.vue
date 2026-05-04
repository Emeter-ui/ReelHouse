<script setup lang="ts">
import 'vidstack/player'
import 'vidstack/player/layouts/default'
import 'vidstack/player/ui'
import 'vidstack/player/styles/default/theme.css'
import 'vidstack/player/styles/default/layouts/video.css'

import { canFetchDirect, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'
import { useContinueWatching } from '~/composables/useContinueWatching'
import type { MediaPlayerElement } from 'vidstack/elements'

type Props = {
  resolved: StreamResolveResponse | null
  pending: boolean
  error: unknown
  /** Identity for Continue Watching */
  contentId: number
  contentType: 'movie' | 'series'
  contentTitle: string
  contentPoster: string | null
  season?: number
  episode?: number
  /** Resolution string like "1080p" — picks the matching entry in resolved.qualities. */
  preferredResolution?: string
}
const props = defineProps<Props>()

const cw = useContinueWatching()
const playerEl = ref<MediaPlayerElement | null>(null)
const finalSrc = ref<string | null>(null)
const probeStatus = ref<'idle' | 'probing' | 'direct' | 'proxied' | 'failed'>('idle')
const videoError = ref<string | null>(null)

// Pick the active stream from qualities[] when a preferredResolution is set;
// otherwise fall back to the server-chosen stream_url.
const activeQuality = computed(() => {
  const list = props.resolved?.qualities ?? []
  const wanted = props.preferredResolution
  if (wanted) {
    const hit = list.find((q) => q.resolution === wanted)
    if (hit) return hit
  }
  return null
})
const activeStreamUrl = computed(
  () => activeQuality.value?.url ?? props.resolved?.stream_url ?? null,
)
const activeCodec = computed(
  () => activeQuality.value?.codec ?? props.resolved?.stream_codec ?? '',
)

watch(
  activeStreamUrl,
  async (url) => {
    if (!url) {
      finalSrc.value = null
      return
    }
    probeStatus.value = 'probing'
    const direct = await canFetchDirect(url)
    if (direct) {
      finalSrc.value = url
      probeStatus.value = 'direct'
    } else {
      finalSrc.value = proxiedUrl(url, props.resolved?.play_referer)
      probeStatus.value = 'proxied'
    }
  },
  { immediate: true },
)

const sourceType = computed(() => {
  const u = (activeStreamUrl.value ?? '').toLowerCase()
  if (u.includes('.m3u8')) return 'application/x-mpegurl'
  const codec = activeCodec.value.toLowerCase()
  const isHevc = codec
    ? codec.includes('hevc') || codec.includes('265')
    : u.includes('/h265/') || u.includes('/hevc/')
  return isHevc ? 'video/mp4; codecs="hvc1"' : 'video/mp4'
})

// Vidstack accepts `{ src, type }` or array of those — explicit type avoids
// MIME guessing on proxy URLs that don't carry a file extension.
const playerSource = computed(() => {
  if (!finalSrc.value) return null
  return { src: finalSrc.value, type: sourceType.value }
})

// Continue Watching restore — applied on first metadata load only so quality
// switches don't snap us back to a stale position.
const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)
let cwRestored = false
const onLoadedMetadata = () => {
  if (cwRestored) return
  if (playerEl.value && previous.value) {
    playerEl.value.currentTime = previous.value.position
  }
  cwRestored = true
}

const onTimeUpdate = () => {
  const p = playerEl.value
  if (!p || !p.duration || isNaN(p.duration)) return
  cw.upsert({
    id: props.contentId,
    type: props.contentType,
    title: props.contentTitle,
    poster: props.contentPoster,
    season: props.season,
    episode: props.episode,
    position: Math.floor(p.currentTime),
    duration: Math.floor(p.duration),
  })
}

const onError = (e: Event) => {
  // Vidstack emits a CustomEvent with detail = { code, message, mediaError }
  const detail = (e as CustomEvent).detail as
    | { code?: number; message?: string }
    | undefined
  const codeMap: Record<number, string> = {
    1: 'aborted',
    2: 'network error',
    3: 'decode error (codec not supported by your browser — likely HEVC/H.265)',
    4: 'source not supported',
  }
  videoError.value =
    (detail?.code && codeMap[detail.code]) ||
    detail?.message ||
    'Playback error'
  probeStatus.value = 'failed'
}

onBeforeUnmount(() => {
  cw.flush()
})

const downloadFilename = computed(() => {
  const safe = (props.contentTitle || 'video').replace(/[\\/:*?"<>|]+/g, ' ').trim()
  if (props.contentType === 'series' && props.season != null && props.episode != null) {
    const s = String(props.season).padStart(2, '0')
    const e = String(props.episode).padStart(2, '0')
    return `${safe} S${s}E${e}.mp4`
  }
  return `${safe}.mp4`
})
</script>

<template>
  <div class="relative w-full aspect-video bg-black rounded-lg overflow-hidden group">
    <!-- Loading overlay -->
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Resolving stream…</span>
      </div>
    </div>

    <!-- Error overlay -->
    <div
      v-else-if="error || !resolved"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300 z-20"
    >
      <div class="max-w-xs space-y-2">
        <p class="font-medium text-red-400">Source unavailable</p>
        <p class="text-sm text-slate-400">The stream could not be resolved. Please try another title or quality.</p>
      </div>
    </div>

    <!-- Vidstack player -->
    <media-player
      v-show="playerSource"
      ref="playerEl"
      :title="contentTitle"
      :src="playerSource"
      :poster="contentPoster ?? undefined"
      crossorigin="anonymous"
      playsinline
      autoplay
      class="w-full h-full"
      @loaded-metadata="onLoadedMetadata"
      @time-update="onTimeUpdate"
      @error="onError"
    >
      <media-provider>
        <track
          v-for="c in (resolved?.captions || [])"
          :key="c.url"
          kind="subtitles"
          :label="c.lang"
          :srclang="c.lang.slice(0, 2).toLowerCase()"
          :src="proxiedUrl(c.url, resolved?.play_referer)"
        />
      </media-provider>
      <media-video-layout></media-video-layout>
    </media-player>

    <!-- UI Overlays (Chips) -->
    <div class="absolute top-4 left-4 flex gap-2 z-10 pointer-events-none">
      <div
        v-if="probeStatus === 'proxied'"
        class="chip bg-black/60 text-amber-200 backdrop-blur-md border border-white/5"
      >
        via proxy
      </div>
    </div>

    <a
      v-if="activeStreamUrl"
      :href="proxiedUrl(activeStreamUrl, resolved?.play_referer)"
      :download="downloadFilename"
      target="_blank"
      rel="noopener"
      class="absolute top-4 right-4 chip bg-black/70 hover:bg-black text-white
             ring-1 ring-white/10 inline-flex items-center gap-2 backdrop-blur-md z-10 transition-all opacity-0 group-hover:opacity-100"
      title="Download this title"
    >
      <span class="text-[10px]">⬇</span> Download
    </a>

    <div
      v-if="videoError"
      class="absolute bottom-20 left-1/2 -translate-x-1/2 chip bg-red-900/90 text-red-100 border border-red-500/50 z-30"
    >
      Playback error: {{ videoError }}
    </div>
  </div>
</template>

<style>
/* Match the existing dark theme — vidstack pulls colors from CSS vars. */
media-player {
  --media-brand: #eab308; /* accent-gold */
  --media-focus-ring-color: #eab308;
  --media-focus-ring: 0 0 0 3px var(--media-focus-ring-color);
  background: #000;
}

/* Ensure the player fills the rounded container */
media-player[data-view-type='video'] {
  border-radius: inherit;
  overflow: hidden;
}
</style>
