<script setup lang="ts">
type Genre = { id: number; name: string }

const props = defineProps<{
  modelValue: { year?: number | ''; genre?: number | ''; sort?: string }
  type: 'movie' | 'tv'
}>()
const emit = defineEmits<{ 'update:modelValue': [value: typeof props.modelValue] }>()

const local = ref({ ...props.modelValue })
watch(local, (v) => emit('update:modelValue', { ...v }), { deep: true })
watch(() => props.modelValue, (v) => (local.value = { ...v }))

const { data: genreData } = useTmdb<{ genres: Genre[] }>(
  `genre/${props.type}/list`,
  {},
  { lazy: true },
)
const genres = computed<Genre[]>(() => genreData.value?.genres ?? [])

const thisYear = new Date().getFullYear()
const years = Array.from({ length: 60 }, (_, i) => thisYear - i)

const sorts =
  props.type === 'movie'
    ? [
        { v: 'popularity.desc', label: 'Popularity ↓' },
        { v: 'popularity.asc', label: 'Popularity ↑' },
        { v: 'vote_average.desc', label: 'Rating ↓' },
        { v: 'release_date.desc', label: 'Newest' },
        { v: 'release_date.asc', label: 'Oldest' },
      ]
    : [
        { v: 'popularity.desc', label: 'Popularity ↓' },
        { v: 'vote_average.desc', label: 'Rating ↓' },
        { v: 'first_air_date.desc', label: 'Newest' },
        { v: 'first_air_date.asc', label: 'Oldest' },
      ]

const reset = () => {
  local.value = { year: '', genre: '', sort: 'popularity.desc' }
}
</script>

<template>
  <aside class="w-full md:w-64 shrink-0 space-y-6">
    <div>
      <div class="text-xs uppercase tracking-wider text-slate-400 mb-2">Year</div>
      <select
        v-model.number="local.year"
        class="w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
      >
        <option value="">Any year</option>
        <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>

    <div>
      <div class="text-xs uppercase tracking-wider text-slate-400 mb-2">Genre</div>
      <select
        v-model.number="local.genre"
        class="w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
      >
        <option value="">Any genre</option>
        <option v-for="g in genres" :key="g.id" :value="g.id">{{ g.name }}</option>
      </select>
    </div>

    <div>
      <div class="text-xs uppercase tracking-wider text-slate-400 mb-2">Sort</div>
      <select
        v-model="local.sort"
        class="w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
      >
        <option v-for="s in sorts" :key="s.v" :value="s.v">{{ s.label }}</option>
      </select>
    </div>

    <button class="btn-ghost w-full justify-center" @click="reset">Reset filters</button>
  </aside>
</template>
