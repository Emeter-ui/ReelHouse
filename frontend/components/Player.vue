<script setup lang="ts">
import 'vidstack/player/styles/default/theme.css'
import 'vidstack/player/styles/default/layouts/video.css'

import { canFetchDirect, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'
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
}
const props = defineProps<Props>()

const cw = useContinueWatching()
const finalSrc = ref<string | null>(null)
const probeStatus = ref<'idle' | 'probing' | 'direct' | 'proxied' | 'failed'>('idle')
const videoError = ref<string | null>(null)

// For Vidstack custom elements
onMounted(() => {
  import('vidstack/elements')
})

const onVideoError = (e: any) => {
  const err = e.detail
  videoError.value = err?.message || 'Playback error'
  probeStatus.value = 'failed'
}

watch(
  () => props.resolved?.stream_url,
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
      finalSrc.value = proxiedUrl(url)
      probeStatus.value = 'proxied'
    }
  },
  { immediate: true },
)

const playerRef = ref<any>(null)

// Restore previous position
const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)

const onLoadedMetadata = (e: any) => {
  const player = e.target
  if (player && previous.value) {
    player.currentTime = previous.value.position
  }
}

const onTimeUpdate = (e: any) => {
  const player = e.target
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

onBeforeUnmount(() => cw.flush())

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
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Resolving stream…</span>
      </div>
    </div>
    
    <div
      v-else-if="error || !resolved"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300"
    >
      <div class="max-w-xs space-y-2">
        <p class="font-medium text-red-400">Source unavailable</p>
        <p class="text-sm text-slate-400">The stream could not be resolved. Please try another title or quality.</p>
      </div>
    </div>

    <media-player
      v-else-if="finalSrc"
      ref="playerRef"
      :src="finalSrc"
      autoplay
      playsinline
      class="w-full h-full"
      @loaded-metadata="onLoadedMetadata"
      @time-update="onTimeUpdate"
      @error="onVideoError"
    >
      <media-provider>
        <track
          v-for="c in resolved.captions"
          :key="c.url"
          kind="subtitles"
          :label="c.lang"
          :srclang="c.lang.slice(0, 2).toLowerCase()"
          :src="proxiedUrl(c.url)"
        />
      </media-provider>
      <media-video-layout />
    </media-player>

    <div
      v-if="probeStatus === 'proxied'"
      class="absolute top-4 left-4 chip bg-black/60 text-amber-200 backdrop-blur-md border border-white/5 z-10"
    >
      via proxy
    </div>
    
    <a
      v-if="resolved?.stream_url"
      :href="resolved.stream_url"
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
      class="absolute bottom-20 left-1/2 -translate-x-1/2 chip bg-red-900/90 text-red-100 border border-red-500/50 z-20"
    >
      Playback error: {{ videoError }}
    </div>
  </div>
</template>

<style scoped>
media-player {
  --video-brand: #eab308; /* accent-gold */
}
</style>

