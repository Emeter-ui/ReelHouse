const KEY = 'reelhouse:v1:searchHistory'
const MAX = 10

function read(): string[] {
  if (!import.meta.client) return []
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((t) => typeof t === 'string') : []
  } catch {
    return []
  }
}

function write(list: string[]) {
  if (!import.meta.client) return
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch (e) {
    console.warn('searchHistory write failed', e)
  }
}

const state = ref<string[]>([])
let bound = false

function bind() {
  if (bound || !import.meta.client) return
  bound = true
  state.value = read()
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) state.value = read()
  })
}

export function useSearchHistory() {
  bind()

  // Most-recent-first; dedupe case-insensitively but keep the user's casing.
  const add = (term: string) => {
    const t = term.trim()
    if (!t) return
    const key = t.toLocaleLowerCase()
    const next = [t, ...state.value.filter((s) => s.toLocaleLowerCase() !== key)].slice(0, MAX)
    state.value = next
    write(next)
  }

  const remove = (term: string) => {
    const key = term.toLocaleLowerCase()
    const next = state.value.filter((s) => s.toLocaleLowerCase() !== key)
    state.value = next
    write(next)
  }

  const clear = () => {
    state.value = []
    write([])
  }

  return {
    items: readonly(state),
    add,
    remove,
    clear,
  }
}
