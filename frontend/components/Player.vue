<script setup lang="ts">
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

const onVideoError = (e: Event) => {
  const v = e.target as HTMLVideoElement
  const code = v?.error?.code
  const map: Record<number, string> = {
    1: 'aborted',
    2: 'network error',
    3: 'decode error',
    4: 'src not supported',
  }
  videoError.value = code ? map[code] ?? `code ${code}` : 'unknown'
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

const videoRef = ref<HTMLVideoElement | null>(null)

// Restore previous position
const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)

const onLoadedMetadata = () => {
  if (videoRef.value && previous.value) {
    videoRef.value.currentTime = previous.value.position
  }
}

const onTimeUpdate = () => {
  const v = videoRef.value
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
  <div class="relative w-full aspect-video bg-black rounded-lg overflow-hidden">
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400">
      Resolving stream…
    </div>
    <div
      v-else-if="error || !resolved"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300"
    >
      Source unavailable — try another title.
    </div>
    <video
      v-else-if="finalSrc"
      ref="videoRef"
      :src="finalSrc"
      controls
      autoplay
      muted
      playsinline
      class="w-full h-full"
      @loadedmetadata="onLoadedMetadata"
      @timeupdate="onTimeUpdate"
      @error="onVideoError"
    >
      <track
        v-for="c in resolved.captions"
        :key="c.url"
        kind="subtitles"
        :label="c.lang"
        :srclang="c.lang.slice(0, 2).toLowerCase()"
        :src="proxiedUrl(c.url)"
      />
    </video>

    <div
      v-if="probeStatus === 'proxied'"
      class="absolute top-2 left-2 chip bg-black/60 text-amber-200"
    >
      via proxy
    </div>
    <a
      v-if="resolved?.stream_url"
      :href="resolved.stream_url"
      :download="downloadFilename"
      target="_blank"
      rel="noopener"
      class="absolute top-2 right-2 chip bg-black/70 hover:bg-black text-white
             ring-1 ring-white/10 inline-flex items-center gap-1"
      title="Download this title"
    >
      ⬇ Download
    </a>
    <div
      v-if="videoError"
      class="absolute bottom-3 left-3 chip bg-red-900/80 text-red-100"
    >
      Playback error: {{ videoError }}
    </div>
  </div>
</template>
