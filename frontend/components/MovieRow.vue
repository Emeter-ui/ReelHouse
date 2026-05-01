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
  <section class="px-6 my-8 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-3 gap-4 flex-wrap">
      <h2 class="text-lg font-semibold tracking-tight">{{ title }}</h2>
      <div v-if="tabs" class="flex gap-2">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="text-xs px-3 py-1 rounded-full transition-colors"
          :class="
            t.key === active
              ? 'bg-white/15 text-white'
              : 'bg-white/5 text-slate-400 hover:bg-white/10'
          "
          @click="active = t.key"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <div v-if="pending && !list.length" class="row-scroll">
      <div
        v-for="i in 8"
        :key="i"
        class="w-40 sm:w-48 aspect-[2/3] rounded-lg bg-white/5 animate-pulse"
      />
    </div>

    <div v-else-if="!list.length" class="text-sm text-slate-500 py-6">
      Nothing to show yet.
    </div>

    <div v-else class="row-scroll">
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
    </div>
  </section>
</template>
