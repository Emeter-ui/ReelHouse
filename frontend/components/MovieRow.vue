<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
type TmdbItem = {
  id: number
  title?: string
  name?: string
  poster_path: string | null
  release_date?: string
  first_air_date?: string
  vote_average?: number
  media_type?: string
}

type Tab = { key: string; label: string; path: string }

const props = defineProps<{
  title: string
  type?: 'movie' | 'series'
  /** Provide either tabs (with TMDB paths) … */
  tabs?: Tab[]
  /** … or a fixed array of items already loaded */
  items?: TmdbItem[]
}>()

const active = ref(props.tabs?.[0]?.key)

const fetched = props.tabs
  ? useTmdb<{ results: TmdbItem[] }>(
      () => props.tabs!.find((t) => t.key === active.value)?.path ?? props.tabs![0].path,
      {},
      { lazy: true },
    )
  : null

const list = computed<TmdbItem[]>(() =>
  props.items ?? fetched?.data.value?.results ?? [],
)
const pending = computed(() => fetched?.pending?.value ?? false)
const inferredType = computed<'movie' | 'series'>(() => props.type ?? 'movie')

const yearOf = (item: TmdbItem) => {
  const d = item.release_date || item.first_air_date
  return d ? Number(d.slice(0, 4)) : null
}
</script>

<template>
  <section class="my-10 max-w-7xl mx-auto">
    <div class="px-6 flex items-center justify-between mb-4 gap-4 flex-wrap">
      <h2 class="text-xl font-bold tracking-tight text-white/90">{{ title }}</h2>
      <div v-if="tabs" class="flex gap-2 bg-white/5 p-1 rounded-full backdrop-blur-sm">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="text-[10px] font-bold uppercase tracking-wider px-4 py-1.5 rounded-full transition-all duration-300"
          :class="
            t.key === active
              ? 'bg-white text-ink-950 shadow-md'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          "
          @click="active = t.key"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <div class="relative group">
      <div v-if="pending && !list.length" class="row-scroll px-6">
        <div
          v-for="i in 8"
          :key="i"
          class="w-36 sm:w-48 md:w-52 aspect-[2/3] rounded-xl bg-white/5 animate-pulse shrink-0"
        />
      </div>

      <div v-else-if="!list.length" class="px-6 text-sm text-slate-500 py-10 text-center glass-panel rounded-2xl mx-6">
        No titles found in this category.
      </div>

      <div v-else class="row-scroll px-6 mask-fade">
        <MovieCard
          v-for="item in list"
          :key="item.id"
          :id="item.id"
          :type="inferredType"
          :title="item.title || item.name || 'Untitled'"
          :poster="item.poster_path"
          :year="yearOf(item)"
          :rating="item.vote_average ?? null"
        />
        <!-- Spacer for scroll end padding -->
        <div class="w-1 shrink-0" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.mask-fade {
  mask-image: linear-gradient(to right, transparent, black 40px, black calc(100% - 40px), transparent);
}
@media (max-width: 640px) {
  .mask-fade {
    mask-image: none;
  }
}
</style>
