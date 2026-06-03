<script setup lang="ts">
import { useTmdb } from '~/composables/useTmdb'
import { useSeriesStream } from '~/composables/useStream'
import { useSeriesStructure } from '~/composables/useSeriesStructure'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const season = computed(() => Number(route.params.season))
const episode = computed(() => Number(route.params.episode))

type Series = {
  id: number
  name: string
  poster_path: string | null
  first_air_date?: string
}

const { data: series } = await useTmdb<Series>(() => `tv/${id.value}`)

// season/episode in the URL are MovieBox-native, so episode metadata and the
// "next" link come from the same structure that defines that numbering — not
// from a TMDB season lookup (whose seasons split differently).
const { data: structure } = useSeriesStructure(
  () => series.value?.name ?? '',
  {
    tmdbId: () => series.value?.id,
    year: () => (series.value?.first_air_date ? series.value.first_air_date.slice(0, 4) : undefined),
  },
)

const ep = computed(() =>
  structure.value?.seasons
    .find((s) => s.se === season.value)
    ?.episodes.find((e) => e.ep === episode.value),
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

// Next episode within the season; roll over to the first episode of the next
// season at a season boundary.
const next = computed<{ se: number; ep: number; name: string } | undefined>(() => {
  const s = structure.value
  if (!s) return undefined
  const seasonsSorted = [...s.seasons].sort((a, b) => a.se - b.se)
  const cur = seasonsSorted.find((x) => x.se === season.value)
  if (!cur) return undefined
  const idx = cur.episodes.findIndex((e) => e.ep === episode.value)
  if (idx >= 0 && idx + 1 < cur.episodes.length) {
    const n = cur.episodes[idx + 1]
    return { se: season.value, ep: n.ep, name: n.name }
  }
  const sIdx = seasonsSorted.findIndex((x) => x.se === season.value)
  const nextSeason = sIdx >= 0 ? seasonsSorted[sIdx + 1] : undefined
  if (nextSeason?.episodes.length) {
    const n = nextSeason.episodes[0]
    return { se: nextSeason.se, ep: n.ep, name: n.name }
  }
  return undefined
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
          :to="`/watch/series/${id}/s/${next.se}/e/${next.ep}`"
          class="btn-primary inline-block"
        >
          Next: E{{ next.ep }} — {{ next.name }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
