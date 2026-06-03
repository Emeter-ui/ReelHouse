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
    class="relative overflow-hidden h-[65vh] min-h-[480px] max-h-[800px] flex items-end"
  >
    <!-- Background Image with Transition -->
    <Transition
      enter-active-class="transition-opacity duration-1000 ease-in-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-1000 ease-in-out"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
      mode="out-in"
    >
      <div :key="current.id" class="absolute inset-0">
        <img
          v-if="current.backdrop_path"
          :src="tmdbImg(current.backdrop_path, 'original')"
          :alt="titleOf(current)"
          class="absolute inset-0 w-full h-full object-cover scale-105 animate-slow-zoom"
        />
        <div class="absolute inset-0 bg-hero-fade" />
        <div class="absolute inset-0 bg-gradient-to-r from-ink-950/80 via-ink-950/20 to-transparent md:block hidden" />
      </div>
    </Transition>

    <div class="relative w-full max-w-7xl mx-auto px-6 pb-16 md:pb-24 z-10">
      <div class="max-w-3xl space-y-6">
        <Transition
          enter-active-class="transition-all duration-700 delay-300 ease-out"
          enter-from-class="translate-y-8 opacity-0"
          enter-to-class="translate-y-0 opacity-100"
          appear
        >
          <div :key="current.id" class="space-y-4">
            <div class="flex items-center gap-3">
              <span v-if="current.vote_average" class="chip bg-accent-gold/20 text-accent-gold border border-accent-gold/20">
                ★ {{ current.vote_average?.toFixed(1) }}
              </span>
              <span v-if="yearOf(current)" class="chip">{{ yearOf(current) }}</span>
              <span class="chip bg-white/5 text-white/60">Trending</span>
            </div>
            
            <h1 class="text-4xl md:text-7xl font-extrabold tracking-tight leading-[1.1] text-white drop-shadow-2xl">
              {{ titleOf(current) }}
            </h1>
            
            <p class="text-slate-300 line-clamp-3 text-base md:text-lg max-w-2xl leading-relaxed font-medium">
              {{ current.overview }}
            </p>

            <div class="flex items-center gap-4 pt-4">
              <NuxtLink :to="playLink(current)" class="btn-accent px-8 py-4 text-base">
                <span class="text-lg">▶</span> Watch Now
              </NuxtLink>
              <NuxtLink :to="detailLink(current)" class="btn-ghost px-8 py-4 text-base">
                More Info
              </NuxtLink>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Indicators -->
      <div v-if="items.length > 1" class="absolute bottom-10 right-6 flex items-center gap-3">
        <button
          v-for="(_, i) in items.slice(0, 5)"
          :key="i"
          class="h-1.5 rounded-full transition-all duration-500"
          :class="i === idx ? 'w-10 bg-white' : 'w-4 bg-white/20 hover:bg-white/40'"
          :aria-label="`Slide ${i + 1}`"
          @click="idx = i"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
@keyframes slow-zoom {
  0% { transform: scale(1); }
  100% { transform: scale(1.1); }
}
.animate-slow-zoom {
  animation: slow-zoom 20s linear infinite alternate;
}
</style>
