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

type Tab = {
  key: string
  label: string
  path: string
  query?: Record<string, string | number | boolean>
}

const props = defineProps<{
  title: string
  type?: 'movie' | 'series'
  /** Provide either tabs (with TMDB paths) … */
  tabs?: Tab[]
  /** … or a fixed array of items already loaded */
  items?: TmdbItem[]
}>()

const active = ref(props.tabs?.[0]?.key)
const activeTab = computed(() =>
  props.tabs?.find((t) => t.key === active.value) ?? props.tabs?.[0],
)

const fetched = props.tabs
  ? useTmdb<{ results: TmdbItem[] }>(
      () => activeTab.value?.path ?? '',
      () => activeTab.value?.query ?? {},
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
  <section class="my-6 md:my-10 max-w-7xl mx-auto">
    <div class="px-4 sm:px-6 flex items-center justify-between mb-3 md:mb-4 gap-3 flex-wrap">
      <h2 class="section-title">{{ title }}</h2>
      <div v-if="tabs" class="flex gap-1 bg-ink-800 p-1 rounded-md">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="text-[10px] font-bold uppercase tracking-wider px-3 md:px-4 py-1.5 rounded transition-colors duration-200"
          :class="
            t.key === active
              ? 'bg-brand-600 text-white'
              : 'text-slate-400 hover:text-white'
          "
          @click="active = t.key"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <div class="relative group">
      <div v-if="pending && !list.length" class="row-scroll px-4 sm:px-6">
        <div
          v-for="i in 8"
          :key="i"
          class="w-28 sm:w-40 md:w-48 aspect-[2/3] rounded-md bg-white/5 animate-pulse shrink-0"
        />
      </div>

      <div v-else-if="!list.length" class="text-sm text-slate-500 py-8 text-center mx-4 sm:mx-6 rounded-md bg-ink-800/60">
        No titles found in this category.
      </div>

      <div v-else class="row-scroll px-4 sm:px-6 mask-fade">
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
  mask-image: linear-gradient(to right, black 0, black calc(100% - 48px), transparent);
}
@media (max-width: 640px) {
  .mask-fade {
    mask-image: none;
  }
}
</style>
