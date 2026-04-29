<script setup lang="ts">
useHead({ title: 'My List — Reelhouse' })

const myList = useMyList()
const cw = useContinueWatching()

const fileInput = ref<HTMLInputElement | null>(null)

const downloadJson = () => {
  if (!import.meta.client) return
  const blob = new Blob([myList.exportJson()], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `reelhouse-mylist-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const onPickFile = () => fileInput.value?.click()

const onFile = async (e: Event) => {
  const t = e.target as HTMLInputElement
  const f = t.files?.[0]
  if (!f) return
  try {
    const text = await f.text()
    myList.importJson(text)
  } catch (err) {
    alert(`Import failed: ${(err as Error).message}`)
  } finally {
    t.value = ''
  }
}

const confirmClear = () => {
  if (window.confirm('Clear My List? This cannot be undone.')) myList.clear()
}
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between mb-6 gap-3 flex-wrap">
      <h1 class="text-2xl font-bold">My List</h1>
      <div class="flex gap-2">
        <button class="btn-ghost" @click="downloadJson">Export</button>
        <button class="btn-ghost" @click="onPickFile">Import</button>
        <button class="btn-ghost text-red-300" @click="confirmClear">Clear</button>
        <input ref="fileInput" type="file" accept="application/json" class="hidden" @change="onFile" />
      </div>
    </div>

    <div v-if="!myList.items.value.length" class="text-slate-400 py-12 text-center">
      Nothing saved yet. Hit "+ My List" on a movie or series to add it.
    </div>
    <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      <MovieCard
        v-for="i in myList.items.value"
        :key="`${i.type}-${i.id}`"
        :id="i.id"
        :type="i.type"
        :title="i.title"
        :poster="i.poster"
        :year="i.year ?? null"
      />
    </div>

    <section v-if="cw.items.value.length" class="mt-12">
      <h2 class="text-lg font-semibold mb-4">Continue Watching</h2>
      <ul class="divide-y divide-white/5 rounded-lg ring-1 ring-white/5 overflow-hidden">
        <li v-for="i in cw.items.value" :key="`${i.type}-${i.id}-${i.season}-${i.episode}`">
          <NuxtLink
            :to="i.type === 'series'
              ? `/watch/series/${i.id}/s/${i.season}/e/${i.episode}`
              : `/watch/movie/${i.id}`"
            class="flex gap-4 p-3 hover:bg-white/5"
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
              <div class="font-medium">{{ i.title }}</div>
              <div v-if="i.type === 'series'" class="text-xs text-slate-400 mt-0.5">
                Season {{ i.season }} · Episode {{ i.episode }}
              </div>
              <div class="mt-3 h-1 rounded bg-white/10 overflow-hidden">
                <div
                  class="h-full bg-accent"
                  :style="{ width: `${Math.min(100, (i.position / (i.duration || 1)) * 100)}%` }"
                />
              </div>
              <div class="text-xs text-slate-500 mt-1">
                {{ Math.floor(i.position / 60) }}m / {{ Math.floor((i.duration || 0) / 60) }}m
              </div>
            </div>
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>
