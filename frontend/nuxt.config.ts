// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },

  // SPA mode — all data comes from the FastAPI backend at runtime; no SEO need.
  ssr: false,
  nitro: {
    preset: 'static'
  },

  modules: ['@nuxtjs/tailwindcss', '@vite-pwa/nuxt'],
  imports: {
    dirs: ['composables']
  },

  pwa: {
    registerType: 'autoUpdate',
    // injectManifest so we can ship a custom sw.js that also loads
    // Monetag's site-verification importScripts alongside Workbox.
    strategies: 'injectManifest',
    srcDir: 'service-worker',
    filename: 'sw.ts',
    injectManifest: {
      globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
    },
    // Static SPA build — everything lives under the generated output dir.
    manifest: {
      name: 'Reelhouse',
      short_name: 'Reelhouse',
      description: 'Reelhouse — personal streaming.',
      lang: 'en',
      start_url: '/',
      scope: '/',
      display: 'standalone',
      // 'any' (not 'portrait') so the video player can lock landscape on
      // fullscreen — a portrait lock here would pin the whole TWA activity
      // to portrait and block that.
      orientation: 'any',
      background_color: '#020617',
      theme_color: '#020617',
      categories: ['entertainment', 'video'],
      icons: [
        { src: '/icons/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icons/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        {
          src: '/icons/maskable-512x512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ],
    },
    client: {
      installPrompt: true,
    },
    devOptions: {
      enabled: false,
    },
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
        { name: 'theme-color', content: '#020617' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent' },
        { name: 'apple-mobile-web-app-title', content: 'Reelhouse' },
        { name: 'mobile-web-app-capable', content: 'yes' },
      ],
      link: [
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/icons/favicon-32x32.png' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/icons/apple-touch-icon.png' },
      ],
      script: [
        {
          src: 'https://quge5.com/88/tag.min.js',
          async: true,
          'data-zone': '258568',
          'data-cfasync': 'false',
        },
      ],
    },
  },

  runtimeConfig: {
    public: {
      // Default points at the deployed FastAPI backend so Netlify/Vercel
      // builds work without per-platform env vars. Local dev sets
      // NUXT_PUBLIC_API_BASE=http://localhost:8003 in frontend/.env.
      apiBase: 'https://reelhouse-backend.fly.dev',
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
