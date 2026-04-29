<script setup lang="ts">
import AppHeader from '~/components/AppHeader.vue'
const route = useRoute()
const isWatch = computed(() => route.path.startsWith('/watch/'))
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <AppHeader v-if="!isWatch" />
    <main class="flex-1">
      <slot />
    </main>
    <footer
      v-if="!isWatch"
      class="mt-16 border-t border-white/5 px-6 py-8 text-xs text-slate-500"
    >
      <div class="max-w-7xl mx-auto flex items-center justify-between">
        <div>© Reelhouse — personal use only</div>
        <div>Metadata by TMDB. Streams via moviebox-api.</div>
      </div>
    </footer>
  </div>
</template>
