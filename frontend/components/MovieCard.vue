<script setup lang="ts">
import { tmdbImg } from '~/composables/useTmdb'
type Props = {
  id: number
  type?: 'movie' | 'series' | 'anime'
  title: string
  /** TMDB path like "/abc.jpg" OR a full URL (anime). Auto-detected. */
  poster: string | null
  year?: number | null
  rating?: number | null
  size?: 'sm' | 'md' | 'full'
}
const props = withDefaults(defineProps<Props>(), {
  type: 'movie',
  size: 'md',
  year: null,
  rating: null,
})

const link = computed(() => {
  if (props.type === 'series') return `/series/${props.id}`
  if (props.type === 'anime') return `/anime/${props.id}`
  return `/movie/${props.id}`
})

const posterSrc = computed(() => {
  if (!props.poster) return ''
  return /^https?:\/\//.test(props.poster) ? props.poster : tmdbImg(props.poster, 'w300')
})

const widthClass = computed(() => {
  if (props.size === 'sm') return 'w-24 sm:w-36'
  if (props.size === 'full') return 'w-full'
  return 'w-28 sm:w-40 md:w-48'
})
</script>

<template>
  <NuxtLink :to="link" class="block group snap-start shrink-0" :class="widthClass">
    <div class="card aspect-[2/3] relative">
      <img
        v-if="posterSrc"
        :src="posterSrc"
        :alt="title"
        loading="lazy"
        class="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
      />
      <div
        v-else
        class="absolute inset-0 flex items-center justify-center text-slate-600 text-3xl bg-ink-800"
      >
        🎬
      </div>

      <!-- Rating chip -->
      <div
        v-if="rating != null && rating > 0"
        class="absolute top-1.5 right-1.5 rounded-sm bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-accent-gold"
      >
        ★ {{ rating.toFixed(1) }}
      </div>

      <!-- Hover play overlay (desktop only) -->
      <div class="absolute inset-0 hidden md:flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-black/40">
        <div class="w-12 h-12 rounded-full bg-brand-600 flex items-center justify-center text-white shadow-lg shadow-brand-600/40">
          <span class="text-lg ml-0.5">▶</span>
        </div>
      </div>
    </div>
    <div class="pt-2">
      <div class="text-xs sm:text-sm font-semibold line-clamp-1 text-white group-hover:text-brand-400 transition-colors">{{ title }}</div>
      <div v-if="year" class="text-[10px] sm:text-xs text-slate-500 mt-0.5 font-medium">{{ year }}</div>
    </div>
  </NuxtLink>
</template>
