<script setup lang="ts">
import { tmdbImg } from '~/composables/useTmdb'
type Props = {
  id: number
  type?: 'movie' | 'series'
  title: string
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

const link = computed(() =>
  props.type === 'series' ? `/series/${props.id}` : `/movie/${props.id}`,
)

const widthClass = computed(() => {
  if (props.size === 'sm') return 'w-28 sm:w-36'
  if (props.size === 'full') return 'w-full'
  return 'w-36 sm:w-48 md:w-52'
})
</script>

<template>
  <NuxtLink :to="link" class="card block group snap-start shrink-0" :class="widthClass">
    <div class="aspect-[2/3] bg-ink-800 relative overflow-hidden">
      <img
        v-if="poster"
        :src="tmdbImg(poster, 'w300')"
        :alt="title"
        loading="lazy"
        class="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
      />
      <div
        v-else
        class="absolute inset-0 flex items-center justify-center text-slate-500 text-3xl"
      >
        🎬
      </div>
      
      <!-- Overlay Gradient -->
      <div class="absolute inset-0 bg-gradient-to-t from-ink-950/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      
      <div
        v-if="rating != null && rating > 0"
        class="absolute top-2 right-2 chip bg-black/60 text-accent-gold ring-1 ring-white/10"
      >
        ★ {{ rating.toFixed(1) }}
      </div>

      <!-- Quick Play Button Overlay -->
      <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-4 group-hover:translate-y-0">
        <div class="w-12 h-12 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center text-white ring-1 ring-white/30 shadow-xl">
          <span class="text-xl ml-1">▶</span>
        </div>
      </div>
    </div>
    <div class="p-3">
      <div class="text-sm font-semibold line-clamp-1 group-hover:text-accent transition-colors">{{ title }}</div>
      <div v-if="year" class="text-xs text-slate-400 mt-0.5 font-medium">{{ year }}</div>
    </div>
  </NuxtLink>
</template>
