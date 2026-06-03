<script setup lang="ts">
defineProps<{
  id: number
  name: string
  backdrop: string | null
  poster?: string | null
}>()
</script>

<template>
  <NuxtLink :to="`/collection/${id}`" class="card block group">
    <div class="aspect-[16/9] relative bg-ink-800">
      <img
        v-if="backdrop"
        :src="tmdbImg(backdrop, 'w780')"
        :alt="name"
        loading="lazy"
        class="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
      />
      <div class="absolute inset-0 bg-card-fade" />
      <div class="absolute bottom-0 left-0 right-0 p-3">
        <div class="text-base font-semibold leading-tight line-clamp-2">{{ name }}</div>
      </div>
    </div>
  </NuxtLink>
</template>
