<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const q = ref('')
const open = ref(false)

const links = [
  { to: '/', label: 'Home' },
  { to: '/movies', label: 'Movies' },
  { to: '/series', label: 'Series' },
  { to: '/collection', label: 'Collections' },
  { to: '/my-list', label: 'My List' },
]

const submitSearch = () => {
  const term = q.value.trim()
  if (!term) return
  router.push(`/search?q=${encodeURIComponent(term)}`)
  open.value = false
}

const isActive = (to: string) =>
  to === '/' ? route.path === '/' : route.path.startsWith(to)
</script>

<template>
  <header
    class="sticky top-0 z-30 backdrop-blur bg-ink-950/70 border-b border-white/5"
  >
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center gap-6">
      <NuxtLink to="/" class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-md bg-brand-gradient" />
        <span class="font-semibold text-lg tracking-tight">Reelhouse</span>
      </NuxtLink>

      <nav class="hidden md:flex items-center gap-1 ml-4">
        <NuxtLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="px-3 py-1.5 rounded-md text-sm transition-colors"
          :class="
            isActive(l.to)
              ? 'bg-white/10 text-white'
              : 'text-slate-300 hover:text-white hover:bg-white/5'
          "
        >
          {{ l.label }}
        </NuxtLink>
      </nav>

      <form
        class="ml-auto flex items-center gap-2"
        @submit.prevent="submitSearch"
      >
        <input
          v-model="q"
          type="search"
          placeholder="Search movies, series…"
          class="hidden sm:block w-64 rounded-full bg-white/5 px-4 py-2 text-sm
                 ring-1 ring-white/10 focus:ring-accent focus:bg-white/10
                 outline-none placeholder:text-slate-500"
        />
        <button
          type="button"
          class="sm:hidden btn-ghost px-3 py-2"
          aria-label="Search"
          @click="open = !open"
        >
          🔍
        </button>
      </form>
    </div>

    <div v-if="open" class="sm:hidden border-t border-white/5 px-6 py-3">
      <form @submit.prevent="submitSearch">
        <input
          v-model="q"
          autofocus
          type="search"
          placeholder="Search…"
          class="w-full rounded-full bg-white/5 px-4 py-2 text-sm ring-1 ring-white/10 outline-none"
        />
      </form>
    </div>
  </header>
</template>
