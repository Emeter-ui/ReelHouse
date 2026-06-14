<script setup lang="ts">
useHead({ title: 'Admin · Reelhouse' })

const { public: { apiBase } } = useRuntimeConfig()
const token = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const stats = ref<{ total_visits: number; active_now: number } | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const refresh = async () => {
  if (!token.value) return
  loading.value = true
  error.value = null
  try {
    stats.value = await $fetch(`${apiBase}/api/stats/summary`, {
      headers: { 'X-Admin-Token': token.value },
    })
    sessionStorage.setItem('rh_admin_token', token.value)
  } catch (e: any) {
    const status = e?.response?.status ?? e?.statusCode
    error.value = status === 401 ? 'Wrong token' : 'Failed to load'
    stats.value = null
  } finally {
    loading.value = false
  }
}

const signIn = async () => {
  await refresh()
  if (stats.value && !timer) {
    timer = setInterval(refresh, 5_000)
  }
}

const signOut = () => {
  sessionStorage.removeItem('rh_admin_token')
  if (timer) { clearInterval(timer); timer = null }
  stats.value = null
  token.value = ''
}

onMounted(() => {
  const saved = sessionStorage.getItem('rh_admin_token')
  if (saved) {
    token.value = saved
    signIn()
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="max-w-md mx-auto px-6 py-12">
    <h1 class="text-2xl font-semibold mb-6">Visitor stats</h1>

    <div v-if="!stats" class="space-y-3">
      <input
        v-model="token"
        type="password"
        placeholder="Admin token"
        class="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 outline-none focus:border-indigo-500"
        @keydown.enter="signIn"
      >
      <button
        :disabled="loading || !token"
        class="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded px-3 py-2 font-medium"
        @click="signIn"
      >
        {{ loading ? 'Loading…' : 'Sign in' }}
      </button>
      <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>
    </div>

    <div v-else class="space-y-4">
      <div class="bg-slate-900 border border-slate-800 rounded p-4">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Total visits</div>
        <div class="text-4xl font-semibold mt-1">{{ stats.total_visits.toLocaleString() }}</div>
        <div class="text-xs text-slate-500 mt-1">Unique sessions ever recorded</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded p-4">
        <div class="text-slate-400 text-xs uppercase tracking-wide">Active now</div>
        <div class="text-4xl font-semibold mt-1">{{ stats.active_now }}</div>
        <div class="text-xs text-slate-500 mt-1">Sessions that pinged in the last 90s</div>
      </div>
      <div class="flex items-center justify-between text-xs text-slate-500 pt-2">
        <span>Auto-refreshes every 5s</span>
        <button class="underline hover:text-slate-300" @click="signOut">Sign out</button>
      </div>
    </div>
  </div>
</template>
