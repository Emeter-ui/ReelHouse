<script setup lang="ts">
import { canFetchDirect, captionsUrl, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'
import { useContinueWatching } from '~/composables/useContinueWatching'

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
const videoElement = ref<HTMLVideoElement | null>(null)
const finalSrc = ref<string | null>(null)
const probeStatus = ref<'idle' | 'probing' | 'direct' | 'proxied' | 'failed'>('idle')
const { public: { apiBase } } = useRuntimeConfig()
const isProdLocalhost = computed(() => {
  if (process.server) return false
  const isProd = window.location.hostname !== 'localhost'
  return isProd && apiBase.includes('localhost')
})
const videoError = ref<string | null>(null)
let hlsInstance: any = null

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

const sourceType = computed(() => {
  const u = (activeStreamUrl.value ?? '').toLowerCase()
  if (u.includes('.m3u8')) return 'application/x-mpegURL'
  const codec = activeCodec.value.toLowerCase()
  const isHevc = codec
    ? codec.includes('hevc') || codec.includes('265')
    : u.includes('/h265/') || u.includes('/hevc/')
  return isHevc ? 'video/mp4; codecs="hvc1"' : 'video/mp4'
})

const onVideoError = () => {
  const err = videoElement.value?.error
  const codeMap: Record<number, string> = {
    1: 'aborted',
    2: 'network error',
    3: 'decode error (codec not supported by your browser — likely HEVC/H.265)',
    4: 'source not supported',
  }
  videoError.value = err ? (codeMap[err.code] || `error code ${err.code}`) : 'Playback error'
  probeStatus.value = 'failed'
}

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

// Continue Watching restore — only on the very first metadata load so quality
// switches don't snap us back to a stale position.
const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)
let cwRestored = false
const onLoadedMetadata = () => {
  if (cwRestored) return
  if (videoElement.value && previous.value) {
    videoElement.value.currentTime = previous.value.position
  }
  cwRestored = true
}

const onTimeUpdate = () => {
  const v = videoElement.value
  if (!v || !v.duration || isNaN(v.duration)) return
  cw.upsert({
    id: props.contentId,
    type: props.contentType,
    title: props.contentTitle,
    poster: props.contentPoster,
    season: props.season,
    episode: props.episode,
    position: Math.floor(v.currentTime),
    duration: Math.floor(v.duration),
  })
}

const applySource = async () => {
  const v = videoElement.value
  if (!v || !finalSrc.value) return

  videoError.value = null

  if (hlsInstance) {
    hlsInstance.destroy()
    hlsInstance = null
  }

  const isHls = finalSrc.value.toLowerCase().includes('.m3u8')
  if (isHls) {
    if (v.canPlayType('application/vnd.apple.mpegurl')) {
      v.src = finalSrc.value
    } else {
      const Hls = (await import('hls.js')).default
      if (Hls.isSupported()) {
        hlsInstance = new Hls()
        hlsInstance.loadSource(finalSrc.value)
        hlsInstance.attachMedia(v)
      } else {
        v.src = finalSrc.value
      }
    }
  } else {
    v.src = finalSrc.value
  }

  // Best-effort autoplay; browsers may require muted autoplay if blocked.
  v.play().catch(() => {
    /* autoplay-blocked is fine; user can click play */
  })
}

watch(finalSrc, applySource)
onMounted(() => applySource())

onBeforeUnmount(() => {
  if (hlsInstance) hlsInstance.destroy()
  cw.flush()
})

</script>

<template>
  <div class="relative w-full aspect-video bg-black rounded-lg overflow-hidden group">
    <!-- Overlay: Loading -->
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Resolving stream…</span>
      </div>
    </div>

    <!-- Overlay: Probing -->
    <div v-else-if="probeStatus === 'probing'" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Connecting to source…</span>
      </div>
    </div>

    <!-- Overlay: Error / Unavailable -->
    <div
      v-else-if="error || !resolved || !activeStreamUrl"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300 z-20 bg-black/40 backdrop-blur-sm"
    >
      <div class="max-w-xs space-y-4">
        <div class="space-y-2">
          <p class="font-semibold text-red-400 flex items-center justify-center gap-2">
            <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            {{ error ? 'Connection Error' : (!resolved || !activeStreamUrl ? 'Source Unavailable' : 'Error') }}
          </p>
          <p class="text-sm text-slate-400 leading-relaxed">
            <template v-if="isProdLocalhost">
              Frontend is trying to reach localhost:8003 from a production site. Please set NUXT_PUBLIC_API_BASE in Vercel settings.
            </template>
            <template v-else-if="error">
              Could not reach the backend server. The request may have timed out or the server is offline.
            </template>
            <template v-else>
              This title is currently unavailable for streaming. It may be coming soon or restricted in your region.
            </template>
          </p>
        </div>
        <button 
          class="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/10 rounded-full text-xs font-medium transition-colors"
          @click="window.location.reload()"
        >
          Try Again
        </button>
      </div>
    </div>

    <!-- Native HTML5 player (browser default UI). crossorigin is required
         for cross-origin <track> subtitles to load. -->
    <video
      v-show="finalSrc"
      ref="videoElement"
      controls
      controlsList="nodownload"
      playsinline
      crossorigin="anonymous"
      :poster="contentPoster ?? undefined"
      class="w-full h-full bg-black"
      @loadedmetadata="onLoadedMetadata"
      @timeupdate="onTimeUpdate"
      @error="onVideoError"
    >
      <source v-if="finalSrc && !finalSrc.includes('.m3u8')" :src="finalSrc" :type="sourceType" />
      <track
        v-for="(c, i) in (resolved?.captions || [])"
        :key="c.url"
        kind="subtitles"
        :label="c.lang"
        :srclang="c.lang.slice(0, 2).toLowerCase()"
        :src="captionsUrl(c.url)"
        :default="i === 0 && c.lang.toLowerCase().startsWith('en')"
      />
    </video>

    <!-- UI Overlays (Chips) -->
    <div class="absolute top-4 left-4 flex gap-2 z-10 pointer-events-none">
      <div
        v-if="probeStatus === 'proxied'"
        class="chip bg-black/60 text-amber-200 backdrop-blur-md border border-white/5"
      >
        via proxy
      </div>
      <div
        v-if="sourceType.includes('hvc')"
        class="chip bg-indigo-900/60 text-indigo-200 backdrop-blur-md border border-white/5"
      >
        HEVC (H.265)
      </div>
    </div>

    <div
      v-if="videoError"
      class="absolute bottom-20 left-1/2 -translate-x-1/2 chip bg-red-900/90 text-red-100 border border-red-500/50 z-30"
    >
      Playback error: {{ videoError }}
    </div>
  </div>
</template>
