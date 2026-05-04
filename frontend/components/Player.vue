<script setup lang="ts">
import { canFetchDirect, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'
import { useContinueWatching } from '~/composables/useContinueWatching'
import type Plyr from 'plyr'

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

const cw = useContinueWatching()
const finalSrc = ref<string | null>(null)
const probeStatus = ref<'idle' | 'probing' | 'direct' | 'proxied' | 'failed'>('idle')
const videoError = ref<string | null>(null)

const videoElement = ref<HTMLVideoElement | null>(null)
let player: Plyr | null = null
let hlsInstance: any = null

const onVideoError = (e: any) => {
  const err = player?.media?.error || e.detail?.error
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
    console.log('[player] active stream_url =', url)
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

// Restore previous position
const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)

const onLoadedMetadata = () => {
  if (player && previous.value) {
    player.currentTime = previous.value.position
  }
}

const onTimeUpdate = () => {
  if (!player || !player.duration || isNaN(player.duration)) return
  cw.upsert({
    id: props.contentId,
    type: props.contentType,
    title: props.contentTitle,
    poster: props.contentPoster,
    season: props.season,
    episode: props.episode,
    position: Math.floor(player.currentTime),
    duration: Math.floor(player.duration),
  })
}

const sourceType = computed(() => {
  const u = (activeStreamUrl.value ?? '').toLowerCase()
  if (u.includes('.m3u8')) return 'application/x-mpegURL'
  // Trust the codec from the play endpoint response; fall back to URL hints
  // only when the field is missing.
  const codec = activeCodec.value.toLowerCase()
  const isHevc = codec
    ? codec.includes('hevc') || codec.includes('265')
    : u.includes('/h265/') || u.includes('/hevc/')
  return isHevc ? 'video/mp4; codecs="hvc1"' : 'video/mp4'
})

onMounted(async () => {
  const PlyrLib = (await import('plyr')).default
  if (videoElement.value) {
    player = new PlyrLib(videoElement.value, {
      autoplay: true,
      controls: [
        'play-large', 'play', 'progress', 'current-time', 'duration',
        'mute', 'volume', 'captions', 'settings', 'pip', 'airplay', 'fullscreen'
      ],
      settings: ['quality', 'speed', 'loop'],
    })

    player.on('ready', onLoadedMetadata)
    player.on('timeupdate', onTimeUpdate)
    player.on('error', onVideoError)
    
    // Initial source setup
    updatePlayerSource()
  }
})

const updatePlayerSource = async () => {
  if (!player || !finalSrc.value) return
  
  const isHls = finalSrc.value.toLowerCase().includes('.m3u8')
  
  // Cleanup previous HLS instance if any
  if (hlsInstance) {
    hlsInstance.destroy()
    hlsInstance = null
  }

  if (isHls) {
    const Hls = (await import('hls.js')).default
    if (Hls.isSupported()) {
      hlsInstance = new Hls()
      hlsInstance.loadSource(finalSrc.value)
      hlsInstance.attachMedia(videoElement.value!)
      hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
        if (player?.config.autoplay) player.play()
      })
    } else if (videoElement.value!.canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS (Safari/iOS)
      videoElement.value!.src = finalSrc.value
    }
  }

  player.source = {
    type: 'video',
    title: props.contentTitle,
    sources: [
      {
        src: finalSrc.value,
        type: sourceType.value,
      },
    ],
    tracks: (props.resolved?.captions || []).map(c => ({
      kind: 'subtitles',
      label: c.lang,
      srclang: c.lang.slice(0, 2).toLowerCase(),
      src: proxiedUrl(c.url, props.resolved?.play_referer),
    }))
  }
}

watch([finalSrc, sourceType], updatePlayerSource)

onBeforeUnmount(() => {
  if (hlsInstance) hlsInstance.destroy()
  if (player) player.destroy()
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
    <!-- Overlay: Loading -->
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Resolving stream…</span>
      </div>
    </div>
    
    <!-- Overlay: Error -->
    <div
      v-else-if="error || !resolved"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300 z-20"
    >
      <div class="max-w-xs space-y-2">
        <p class="font-medium text-red-400">Source unavailable</p>
        <p class="text-sm text-slate-400">The stream could not be resolved. Please try another title or quality.</p>
      </div>
    </div>

    <!-- The Player -->
    <div v-show="finalSrc" class="w-full h-full">
      <video
        ref="videoElement"
        playsinline
        class="w-full h-full"
      ></video>
    </div>

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
/* Custom Plyr adjustments to match theme */
:root {
  --plyr-color-main: #eab308; /* accent-gold */
  --plyr-video-background: #000;
  --plyr-menu-background: rgba(15, 23, 42, 0.95);
  --plyr-menu-color: #f8fafc;
}

.plyr--full-ui input[type=range] {
  color: var(--plyr-color-main);
}

.plyr__control--overlaid {
  background: rgba(234, 179, 8, 0.8);
}

.plyr--video .plyr__control.plyr__tab-focus, 
.plyr--video .plyr__control:hover, 
.plyr--video .plyr__control[aria-expanded=true] {
  background: var(--plyr-color-main);
  color: #000;
}
</style>

