<script setup lang="ts">
import { useWatchHistory } from '~/composables/useWatchHistory'
import { tmdbImg } from '~/composables/useTmdb'

useHead({ title: 'Watch History — Reelhouse' })

const wh = useWatchHistory()
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Watch History</h1>
      <button
        v-if="wh.items.value.length"
        class="text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-full ring-1 ring-white/10 hover:bg-white/5 transition-colors"
        @click="wh.clear()"
      >
        Clear history
      </button>
    </div>

    <div v-if="!wh.items.value.length" class="text-slate-400 py-12 text-center">
      You haven't watched anything yet.
    </div>

    <ul v-else class="divide-y divide-white/5 rounded-lg ring-1 ring-white/5 overflow-hidden">
      <li
        v-for="i in wh.items.value"
        :key="`${i.type}-${i.id}-${i.season}-${i.episode}`"
        class="group/item flex items-center hover:bg-white/5 transition-colors"
      >
        <NuxtLink
          :to="i.type === 'series'
            ? `/watch/series/${i.id}/s/${i.season}/e/${i.episode}`
            : `/watch/movie/${i.id}`"
          class="flex-1 flex gap-4 p-3 min-w-0"
        >
          <div class="w-24 aspect-[2/3] rounded-md bg-ink-800 overflow-hidden shrink-0">
            <img
              v-if="i.poster"
              :src="tmdbImg(i.poster, 'w300')"
              :alt="i.title"
              class="w-full h-full object-cover"
            />
          </div>
          <div class="min-w-0 flex-1 py-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-slate-100">{{ i.title }}</span>
              <span
                v-if="i.completed"
                class="text-[10px] uppercase tracking-wide text-emerald-300/90 bg-emerald-500/10 ring-1 ring-emerald-500/20 rounded-full px-2 py-0.5"
              >
                Watched
              </span>
            </div>
            <div v-if="i.type === 'series'" class="text-xs text-slate-400 mt-0.5">
              Season {{ i.season }} · Episode {{ i.episode }}
            </div>
            <div class="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div
                class="h-full bg-accent rounded-full"
                :style="{ width: `${i.completed ? 100 : Math.min(100, (i.position / (i.duration || 1)) * 100)}%` }"
              />
            </div>
            <div class="text-xs text-slate-500 mt-1">
              {{ Math.floor(i.position / 60) }}m / {{ Math.floor((i.duration || 0) / 60) }}m
            </div>
          </div>
        </NuxtLink>
        <button
          type="button"
          :aria-label="`Remove ${i.title} from history`"
          class="p-2 mr-3 rounded-full text-slate-500 hover:text-red-400 hover:bg-white/10 opacity-0 group-hover/item:opacity-100 focus:opacity-100 transition-opacity flex-shrink-0"
          @click="wh.remove(i.id, i.type, i.season, i.episode)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4">
            <path d="M3 6h18" />
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6" />
            <path d="M14 11v6" />
          </svg>
        </button>
      </li>
    </ul>
  </div>
</template>
