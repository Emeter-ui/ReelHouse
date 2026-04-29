<script setup lang="ts">
const props = defineProps<{ error: { statusCode: number; message: string } }>()
const handle = () => clearError({ redirect: '/' })
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-6">
    <div class="max-w-md text-center space-y-4">
      <div class="text-6xl font-bold bg-brand-gradient bg-clip-text text-transparent">
        {{ props.error?.statusCode || 'Oops' }}
      </div>
      <h1 class="text-xl font-semibold">{{ props.error?.message || 'Something went wrong.' }}</h1>
      <button class="btn-primary" @click="handle">Back to home</button>
    </div>
  </div>
</template>
