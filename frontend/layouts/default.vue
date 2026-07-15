<script setup lang="ts">
import AppHeader from '~/components/AppHeader.vue'
const route = useRoute()
const isWatch = computed(() => route.path.startsWith('/watch/'))
const year = new Date().getFullYear()
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <AppHeader v-if="!isWatch" />
    <main class="flex-1">
      <slot />
    </main>
    <footer
      v-if="!isWatch"
      class="mt-10 md:mt-16 border-t border-white/5 bg-ink-950"
    >
      <div class="max-w-7xl mx-auto px-4 sm:px-6 py-10 grid grid-cols-1 sm:grid-cols-3 gap-8">
        <!-- Brand column -->
        <div>
          <NuxtLink to="/" class="flex items-center gap-2 mb-3">
            <div class="w-8 h-8 rounded-md bg-brand-600 flex items-center justify-center text-white font-black">R</div>
            <span class="font-extrabold text-xl text-white">Reel<span class="text-brand-400">house</span></span>
          </NuxtLink>
          <p class="text-sm text-slate-400 leading-relaxed">
            Stream trending movies, series and anime — everything in one house.
          </p>
        </div>

        <!-- Useful links column -->
        <div>
          <h3 class="text-xs font-bold uppercase tracking-widest text-white mb-3 flex items-center gap-2">
            <span class="inline-block h-3 w-1 rounded-sm bg-brand-500" />
            Useful Links
          </h3>
          <ul class="space-y-2 text-sm text-slate-400">
            <li><NuxtLink to="/" class="hover:text-brand-400 transition-colors">Home</NuxtLink></li>
            <li><NuxtLink to="/movies" class="hover:text-brand-400 transition-colors">Movies</NuxtLink></li>
            <li><NuxtLink to="/series" class="hover:text-brand-400 transition-colors">Series</NuxtLink></li>
            <li><NuxtLink to="/anime" class="hover:text-brand-400 transition-colors">Anime</NuxtLink></li>
            <li><NuxtLink to="/donghua" class="hover:text-brand-400 transition-colors">Donghua</NuxtLink></li>
            <li><NuxtLink to="/collection" class="hover:text-brand-400 transition-colors">Collections</NuxtLink></li>
          </ul>
        </div>

        <!-- Meta / credits column -->
        <div>
          <h3 class="text-xs font-bold uppercase tracking-widest text-white mb-3 flex items-center gap-2">
            <span class="inline-block h-3 w-1 rounded-sm bg-brand-500" />
            About
          </h3>
          <ul class="space-y-2 text-sm text-slate-400">
            <li>Personal use only.</li>
            <li>Metadata by <span class="text-slate-300">TMDB</span></li>
            <li>Streams via <span class="text-slate-300">moviebox-api</span></li>
            <li>Anime data by <span class="text-slate-300">AniList</span></li>
          </ul>
        </div>
      </div>

      <div class="border-t border-white/5">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4 text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>© {{ year }} Mymuvies — All rights reserved.</div>
          <div>Made for movie nights.</div>
        </div>
      </div>
    </footer>
  </div>
</template>
