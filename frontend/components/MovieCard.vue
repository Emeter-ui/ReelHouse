<script setup lang="ts">
type Props = {
  id: number
  type?: 'movie' | 'series'
  title: string
  poster: string | null
  year?: number | null
  rating?: number | null
  size?: 'sm' | 'md'
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

const widthClass = computed(() =>
  props.size === 'sm' ? 'w-32 sm:w-36' : 'w-40 sm:w-48',
)
</script>

<template>
  <NuxtLink :to="link" class="card block group snap-start" :class="widthClass">
    <div class="aspect-[2/3] bg-ink-800 relative">
      <img
        v-if="poster"
        :src="tmdbImg(poster, 'w300')"
        :alt="title"
        loading="lazy"
        class="absolute inset-0 w-full h-full object-cover"
      />
      <div
        v-else
        class="absolute inset-0 flex items-center justify-center text-slate-500 text-3xl"
      >
        🎬
      </div>
      <div class="absolute inset-0 bg-card-fade opacity-0 group-hover:opacity-100 transition-opacity" />
      <div
        v-if="rating != null && rating > 0"
        class="absolute top-2 right-2 chip bg-black/60 text-accent-gold"
      >
        ★ {{ rating.toFixed(1) }}
      </div>
    </div>
    <div class="p-2">
      <div class="text-sm font-medium line-clamp-1">{{ title }}</div>
      <div v-if="year" class="text-xs text-slate-400">{{ year }}</div>
    </div>
  </NuxtLink>
</template>
