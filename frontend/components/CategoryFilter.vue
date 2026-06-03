<script setup lang="ts">
const props = defineProps<{
  options: Array<{ key: string; label: string }>
  modelValue: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <button
      v-for="o in props.options"
      :key="o.key"
      class="text-xs px-3 py-1.5 rounded-full transition-colors"
      :class="
        o.key === modelValue
          ? 'bg-white text-slate-900'
          : 'bg-white/5 text-slate-300 hover:bg-white/10'
      "
      @click="emit('update:modelValue', o.key)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
