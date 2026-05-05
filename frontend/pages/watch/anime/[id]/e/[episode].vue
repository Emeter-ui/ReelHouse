<script setup lang="ts">
import { animeDetail, animeTitle, animeSearchTitle } from '~/composables/useAnilist'
import type { StreamResolveResponse } from '~/composables/useStream'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const episode = computed(() => Number(route.params.episode))

const anime = await animeDetail(id.value)

useHead({
  title: () =>
    `${animeTitle(anime.title)} · E${episode.value} — Reelhouse`,
})

// Resolve stream via existing /api/stream/series with anilist context.
const { public: { apiBase } } = useRuntimeConfig()
const resolved = ref<StreamResolveResponse | null>(null)
const pending = ref(true)
const error = ref<unknown>(null)

const fetchStream = async () => {
  pending.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      anilist_id: String(anime.id),
      title: animeSearchTitle(anime.title),
      season: '1',
      episode: String(episode.value),
    })
    if (anime.seasonYear) params.set('year', String(anime.seasonYear))
    resolved.value = await $fetch<StreamResolveResponse>(
      `${apiBase}/api/stream/series?${params.toString()}`,
    )
  } catch (e) {
    error.value = e
  } finally {
    pending.value = false
  }
}
watch(() => episode.value, fetchStream, { immediate: true })

const preferredResolution = computed(() => {
  const q = route.query.q
  return typeof q === 'string' && q ? q : undefined
})

const next = computed(() => {
  if (!anime.episodes) return undefined
  return episode.value < anime.episodes ? episode.value + 1 : undefined
})
</script>

<template>
  <div class="min-h-screen bg-black">
    <header class="px-4 sm:px-6 py-3 flex items-center gap-3">
      <button class="btn-ghost" @click="router.back()">← Back</button>
      <div class="font-medium truncate">
        {{ animeTitle(anime.title) }}
        <span class="text-slate-400 text-sm ml-2">E{{ episode }}</span>
      </div>
    </header>

    <div class="max-w-6xl mx-auto px-2 sm:px-4">
      <Player
        :resolved="resolved"
        :pending="pending"
        :error="error"
        :content-id="anime.id"
        content-type="series"
        :content-title="animeTitle(anime.title)"
        :content-poster="anime.coverImage.large || anime.coverImage.medium || null"
        :season="1"
        :episode="episode"
        :preferred-resolution="preferredResolution"
      />

      <div class="px-2 py-4 max-w-3xl space-y-3">
        <NuxtLink
          v-if="next"
          :to="`/watch/anime/${id}/e/${next}`"
          class="btn-primary inline-block"
        >
          Next: E{{ next }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>
