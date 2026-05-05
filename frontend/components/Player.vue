<script setup lang="ts">
import videojs from 'video.js'
import 'video.js/dist/video-js.css'
import { canFetchDirect, captionsUrl, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'
import { useContinueWatching } from '~/composables/useContinueWatching'

type VjsPlayer = ReturnType<typeof videojs>

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
let player: VjsPlayer | null = null
let remoteTracks: HTMLTrackElement[] = []
const reloadPage = () => location.reload()

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

// MovieBox returns captions in arbitrary order — English is rarely first.
const defaultCaptionUrl = computed(() => {
  const list = props.resolved?.captions ?? []
  return list.find((c) => c.lang?.toLowerCase().startsWith('en'))?.url ?? null
})

// `<track srclang>` requires a valid BCP 47 tag. MovieBox sometimes labels
// captions in their own scripts ("اَلْعَرَبِيَّةُ"); the slice would be non-ASCII
// and rejected by browsers. Fall back to "und".
const toSrcLang = (lang: string): string => {
  const slug = (lang || '').slice(0, 2).toLowerCase()
  return /^[a-z]{2}$/.test(slug) ? slug : 'und'
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

const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)
let cwRestored = false

const upsertProgress = () => {
  if (!player) return
  const cur = player.currentTime() ?? 0
  const dur = player.duration() ?? 0
  if (!dur || isNaN(dur)) return
  cw.upsert({
    id: props.contentId,
    type: props.contentType,
    title: props.contentTitle,
    poster: props.contentPoster,
    season: props.season,
    episode: props.episode,
    position: Math.floor(cur),
    duration: Math.floor(dur),
  })
}

// Re-add captions to the player. Remote tracks added with manualCleanup=true
// persist across source changes, so we remove them explicitly when the
// captions list changes (e.g. when navigating to a different episode).
const syncCaptions = () => {
  if (!player) return
  for (const el of remoteTracks) player.removeRemoteTextTrack(el)
  remoteTracks = []
  const captions = props.resolved?.captions ?? []
  const defaultUrl = defaultCaptionUrl.value
  for (const c of captions) {
    const trackEl = player.addRemoteTextTrack(
      {
        kind: 'subtitles',
        label: c.lang,
        srclang: toSrcLang(c.lang),
        src: captionsUrl(c.url),
        default: c.url === defaultUrl,
      },
      true,
    )
    if (trackEl) remoteTracks.push(trackEl as unknown as HTMLTrackElement)
  }
}

const applySource = () => {
  if (!player || !finalSrc.value) return
  videoError.value = null
  player.src({ src: finalSrc.value, type: sourceType.value })
  player.play()?.catch(() => {
    /* autoplay-blocked is fine; user can click play */
  })
}

const initPlayer = () => {
  if (player || !videoElement.value) return
  player = videojs(videoElement.value, {
    controls: true,
    preload: 'auto',
    fluid: false,
    fill: true,
    responsive: true,
    playsinline: true,
    crossOrigin: 'anonymous',
    poster: props.contentPoster ?? undefined,
    controlBar: {
      pictureInPictureToggle: true,
      remainingTimeDisplay: true,
      subsCapsButton: true,
    },
    html5: {
      vhs: { overrideNative: true },
    },
  })

  player.on('loadedmetadata', () => {
    if (cwRestored) return
    if (previous.value && player) {
      player.currentTime(previous.value.position)
    }
    cwRestored = true
  })

  player.on('timeupdate', upsertProgress)

  player.on('error', () => {
    const err = player?.error()
    const codeMap: Record<number, string> = {
      1: 'aborted',
      2: 'network error',
      3: 'decode error (codec not supported by your browser — likely HEVC/H.265)',
      4: 'source not supported',
    }
    videoError.value = err
      ? codeMap[err.code] || `error code ${err.code}`
      : 'Playback error'
    probeStatus.value = 'failed'
  })

  // First source + captions if already resolved by the time we mount.
  if (finalSrc.value) applySource()
  syncCaptions()
}

watch(finalSrc, applySource)
watch(
  [() => props.resolved?.captions, defaultCaptionUrl],
  syncCaptions,
)

onMounted(() => initPlayer())

onBeforeUnmount(() => {
  cw.flush()
  if (player) {
    player.dispose()
    player = null
  }
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
          @click="reloadPage"
        >
          Try Again
        </button>
      </div>
    </div>

    <!-- video.js mounts inside this <video> element. crossOrigin propagates
         to <track> requests so VTT subtitles load over CORS. -->
    <div v-show="finalSrc" class="absolute inset-0 w-full h-full">
      <video
        ref="videoElement"
        class="video-js vjs-default-skin vjs-big-play-centered w-full h-full"
        playsinline
      />
    </div>

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

<style>
/* Make the video.js skin fill its container instead of using vjs-fluid's
   intrinsic aspect ratio (we already enforce 16:9 on the wrapper). */
.video-js {
  width: 100%;
  height: 100%;
  background: #000;
}
.video-js .vjs-tech {
  object-fit: contain;
}
/* Brand the player in our accent gold to match the rest of the UI. */
.video-js .vjs-play-progress,
.video-js .vjs-volume-level,
.video-js .vjs-slider-bar {
  background-color: #eab308;
}
.video-js .vjs-big-play-button {
  background-color: rgba(0, 0, 0, 0.6);
  border-color: rgba(255, 255, 255, 0.2);
  border-radius: 9999px;
}
</style>
