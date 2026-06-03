<script setup lang="ts">
useHead({ title: 'Collections — Reelhouse' })

// TMDB has no public "list collections" endpoint, so we curate well-known
// collection IDs. Each entry is fetched on-demand from /collection/{id}.
// IDs verified against themoviedb.org collection pages.
const featured = [
  { id: 86311, name: 'The Avengers' },
  { id: 10, name: 'Star Wars' },
  { id: 1241, name: 'Harry Potter' },
  { id: 119, name: 'The Lord of the Rings' },
  { id: 295, name: 'Pirates of the Caribbean' },
  { id: 645, name: 'James Bond' },
  { id: 9485, name: 'The Fast and the Furious' },
  { id: 87359, name: 'Mission: Impossible' },
  { id: 8091, name: 'Alien' },
  { id: 528, name: 'The Terminator' },
  { id: 263, name: 'The Dark Knight' },
  { id: 2980, name: 'Ghostbusters' },
  { id: 9888, name: 'Rocky' },
  { id: 8650, name: 'Indiana Jones' },
  { id: 1709, name: 'Rambo' },
  { id: 8945, name: 'Mad Max' },
]

type Collection = {
  id: number
  name: string
  overview: string
  backdrop_path: string | null
  poster_path: string | null
}

const { data: list } = await useAsyncData('collections:featured', async () => {
  const settled = await Promise.allSettled(
    featured.map((c) =>
      $fetch<Collection>(
        `${useRuntimeConfig().public.apiBase}/api/tmdb/collection/${c.id}`,
      ),
    ),
  )
  return settled
    .filter((r): r is PromiseFulfilledResult<Collection> => r.status === 'fulfilled')
    .map((r) => r.value)
})

const hero = computed<Collection | undefined>(() => list.value?.[0])
const rest = computed<Collection[]>(() => list.value?.slice(1) ?? [])
</script>

<template>
  <div>
    <section v-if="hero" class="relative h-[40vh] min-h-[280px] overflow-hidden">
      <img
        v-if="hero.backdrop_path"
        :src="tmdbImg(hero.backdrop_path, 'original')"
        :alt="hero.name"
        class="absolute inset-0 w-full h-full object-cover"
      />
      <div class="absolute inset-0 bg-hero-fade" />
      <div class="relative h-full max-w-7xl mx-auto px-6 flex flex-col justify-end pb-8">
        <div class="text-xs text-slate-300 uppercase tracking-wider">Featured collection</div>
        <h1 class="text-3xl md:text-5xl font-bold tracking-tight mt-2">{{ hero.name }}</h1>
        <p class="text-slate-300 line-clamp-2 max-w-2xl mt-3 text-sm md:text-base">
          {{ hero.overview }}
        </p>
        <NuxtLink :to="`/collection/${hero.id}`" class="btn-primary mt-4 w-fit">Browse</NuxtLink>
      </div>
    </section>

    <div class="max-w-7xl mx-auto px-6 py-8">
      <h2 class="text-xl font-semibold mb-4">All Collections</h2>
      <div v-if="!list" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="i in 6" :key="i" class="aspect-[16/9] rounded-lg bg-white/5 animate-pulse" />
      </div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <CollectionCard
          v-for="c in rest"
          :key="c.id"
          :id="c.id"
          :name="c.name"
          :backdrop="c.backdrop_path"
          :poster="c.poster_path"
        />
      </div>
    </div>
  </div>
</template>
