import type { Config } from 'tailwindcss'

export default <Partial<Config>>{
  content: [
    './components/**/*.{vue,js,ts}',
    './layouts/**/*.vue',
    './pages/**/*.vue',
    './plugins/**/*.{js,ts}',
    './app.vue',
    './error.vue',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#020617',
          900: '#0f172a',
          800: '#1e293b',
          700: '#334155',
        },
        accent: {
          DEFAULT: '#3b82f6',
          500: '#3b82f6',
          400: '#60a5fa',
          cyan: '#22d3ee',
          purple: '#a855f7',
          pink: '#ec4899',
          gold: '#eab308',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'hero-fade': 'linear-gradient(to top, #020617 5%, rgba(2,6,23,0.6) 40%, rgba(2,6,23,0) 100%)',
        'card-fade': 'linear-gradient(to top, rgba(2,6,23,0.95) 0%, rgba(2,6,23,0) 70%)',
        'brand-gradient': 'linear-gradient(135deg, #3b82f6 0%, #a855f7 50%, #ec4899 100%)',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(96,165,250,0.5), 0 8px 30px rgba(59,130,246,0.25)',
      },
    },
  },
  plugins: [],
}
