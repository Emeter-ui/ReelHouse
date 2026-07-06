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
          950: '#050505',
          900: '#0d0d0d',
          800: '#171717',
          700: '#262626',
        },
        brand: {
          DEFAULT: '#7c3aed',
          50:  '#f5f3ff',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
        },
        accent: {
          DEFAULT: '#7c3aed',
          500: '#8b5cf6',
          400: '#a78bfa',
          cyan: '#22d3ee',
          purple: '#a855f7',
          pink: '#ec4899',
          gold: '#eab308',
          red: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'hero-fade': 'linear-gradient(to top, #050505 5%, rgba(5,5,5,0.6) 40%, rgba(5,5,5,0) 100%)',
        'hero-side': 'linear-gradient(to right, rgba(5,5,5,0.9) 0%, rgba(5,5,5,0.4) 40%, rgba(5,5,5,0) 100%)',
        'card-fade': 'linear-gradient(to top, rgba(5,5,5,0.95) 0%, rgba(5,5,5,0) 70%)',
        'brand-gradient': 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(139,92,246,0.5), 0 8px 30px rgba(124,58,237,0.35)',
      },
      transitionProperty: {
        'height': 'height',
        'spacing': 'margin, padding',
      }
    },
  },
  plugins: [],
}
