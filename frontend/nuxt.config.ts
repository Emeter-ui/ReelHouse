// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },

  // SPA mode — all data comes from the FastAPI backend at runtime; no SEO need.
  ssr: false,
  nitro: {
    preset: 'static'
  },

  modules: ['@nuxtjs/tailwindcss'],
  imports: {
    dirs: ['composables']
  },

  css: ['~/assets/css/main.css'],

  app: {
    head: {
      title: 'Reelhouse',
      htmlAttrs: { lang: 'en', class: 'dark' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Reelhouse — personal streaming.' },
        { name: 'color-scheme', content: 'dark' },
      ],
      link: [{ rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' }],
    },
  },

  runtimeConfig: {
    public: {
      apiBase: 'http://localhost:8003', // overridden by NUXT_PUBLIC_API_BASE in .env
      tmdbImageBase: 'https://image.tmdb.org/t/p',
    },
  },

  vue: {
    compilerOptions: {
      // vidstack ships custom elements like <media-player>
      isCustomElement: (tag) => tag.startsWith('media-'),
    },
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },
})
