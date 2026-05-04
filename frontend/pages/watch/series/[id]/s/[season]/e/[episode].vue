<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
import { useSeriesStream } from '~/composables/useStream'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const season = computed(() => Number(route.params.season))
const episode = computed(() => Number(route.params.episode))

type Series = {
  id: number
  name: string
  poster_path: string | null
}
type Episode = {
  id: number
  name: string
  overview: string
  episode_number: number
  still_path: string | null
}
type Season = { episodes: Episode[] }

const { data: series } = await useTmdb<Series>(() => `tv/${id.value}`)
const { data: seasonData } = await useTmdb<Season>(
  () => `tv/${id.value}/season/${season.value}`,
)

const ep = computed<Episode | undefined>(() =>
  seasonData.value?.episodes?.find((e) => e.episode_number === episode.value),
)

useHead({
  title: () =>
    series.value && ep.value
      ? `${series.value.name} · S${season.value} E${episode.value}: ${ep.value.name}`
      : 'Watching',
})

const { data: resolved, pending, error } = useSeriesStream(
  id,
  () => series.value?.name ?? '',
  season,
  episode,
)

const preferredResolution = computed(() => {
  const q = route.query.q
  return typeof q === 'string' && q ? q : undefined
})

const next = computed<Episode | undefined>(() => {
  if (!seasonData.value || !ep.value) return undefined
  return seasonData.value.episodes.find((e) => e.episode_number === episode.value + 1)
})
</script>

<template>
  <div class="min-h-screen bg-black">
    <header class="px-4 sm:px-6 py-3 flex items-center gap-3">
      <button class="btn-ghost" @click="router.back()">← Back</button>
      <div v-if="series" class="font-medium truncate">
        {{ series.name }}
        <span class="text-slate-400 text-sm ml-2">S{{ season }} · E{{ episode }}</span>
      </div>
    </header>

    <div class="max-w-6xl mx-auto px-2 sm:px-4">
      <Player
        v-if="series"
        :resolved="resolved"
        :pending="pending"
        :error="error"
        :content-id="series.id"
        content-type="series"
        :content-title="series.name"
        :content-poster="series.poster_path"
        :season="season"
        :episode="episode"
        :preferred-resolution="preferredResolution"
      />

      <div class="px-2 py-4 max-w-3xl space-y-3">
        <h2 v-if="ep" class="text-lg font-semibold">{{ ep.name }}</h2>
        <p v-if="ep?.overview" class="text-sm text-slate-300">{{ ep.overview }}</p>
        <NuxtLink
          v-if="next"
          :to="`/watch/series/${id}/s/${season}/e/${next.episode_number}`"
          class="btn-primary inline-block"
        >
          Next: E{{ next.episode_number }} — {{ next.name }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
