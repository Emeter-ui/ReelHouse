<script setup lang="ts">
import { canFetchDirect, proxiedUrl, type StreamResolveResponse } from '~/composables/useStream'

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
      playsinline
      class="w-full h-full"
      @loadedmetadata="onLoadedMetadata"
      @timeupdate="onTimeUpdate"
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
  </div>
</template>
