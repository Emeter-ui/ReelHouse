<script setup lang="ts">
import { tmdbImg } from '~/composables/useTmdb'
type TmdbItem = {
  id: number
  title?: string
  name?: string
  overview?: string
  backdrop_path: string | null
  poster_path: string | null
  release_date?: string
  first_air_date?: string
  vote_average?: number
  media_type?: string
}

const props = defineProps<{ items: TmdbItem[]; type?: 'movie' | 'series' }>()
const idx = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => {
    idx.value = (idx.value + 1) % Math.max(1, props.items.length)
  }, 7000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const current = computed(() => props.items[idx.value])
const titleOf = (it?: TmdbItem) => it?.title || it?.name || ''
const yearOf = (it?: TmdbItem) => {
  const d = it?.release_date || it?.first_air_date
  return d ? d.slice(0, 4) : ''
}
const detailLink = (it?: TmdbItem) => {
  if (!it) return '/'
  const t = props.type ?? (it.media_type === 'tv' ? 'series' : 'movie')
  return t === 'series' ? `/series/${it.id}` : `/movie/${it.id}`
}
const playLink = (it?: TmdbItem) => {
  if (!it) return '/'
  const t = props.type ?? (it.media_type === 'tv' ? 'series' : 'movie')
  return t === 'series' ? `/watch/series/${it.id}/s/1/e/1` : `/watch/movie/${it.id}`
}
</script>

<template>
  <section
    v-if="current"
    class="relative overflow-hidden h-[55vh] min-h-[360px] max-h-[640px]"
  >
    <img
      v-if="current.backdrop_path"
      :src="tmdbImg(current.backdrop_path, 'original')"
      :alt="titleOf(current)"
      class="absolute inset-0 w-full h-full object-cover"
    />
    <div class="absolute inset-0 bg-hero-fade" />

    <div class="relative h-full max-w-7xl mx-auto px-6 flex flex-col justify-end pb-10">
      <div class="max-w-2xl space-y-3">
        <div class="flex items-center gap-2 text-xs">
          <span v-if="current.vote_average" class="chip text-accent-gold">★ {{ current.vote_average?.toFixed(1) }}</span>
          <span v-if="yearOf(current)" class="chip">{{ yearOf(current) }}</span>
        </div>
        <h1 class="text-3xl md:text-5xl font-bold tracking-tight">
          {{ titleOf(current) }}
        </h1>
        <p class="text-slate-300 line-clamp-3 text-sm md:text-base">
          {{ current.overview }}
        </p>
        <div class="flex items-center gap-3 pt-1">
          <NuxtLink :to="playLink(current)" class="btn-primary">▶ Play</NuxtLink>
          <NuxtLink :to="detailLink(current)" class="btn-ghost">Details</NuxtLink>
        </div>
      </div>

      <div v-if="items.length > 1" class="absolute bottom-4 right-6 flex gap-1">
        <button
          v-for="(_, i) in items.slice(0, 5)"
          :key="i"
          class="w-8 h-1 rounded-full transition-colors"
          :class="i === idx ? 'bg-white' : 'bg-white/30'"
          :aria-label="`Slide ${i + 1}`"
          @click="idx = i"
        />
      </div>
    </div>
  </section>
</template>
