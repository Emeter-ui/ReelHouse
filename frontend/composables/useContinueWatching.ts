export type ContinueWatchingItem = {
  id: number
  type: 'movie' | 'series'
  title: string
  poster: string | null
  season?: number
  episode?: number
  position: number   // seconds
  duration: number   // seconds
  updatedAt: number
}

const KEY = 'reelhouse:v1:continueWatching'
const MAX = 100
const ADD_AFTER_SECONDS = 30
const COMPLETE_FRACTION = 0.95

function read(): ContinueWatchingItem[] {
  if (!import.meta.client) return []
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as ContinueWatchingItem[]) : []
  } catch {
    return []
  }
}

function write(list: ContinueWatchingItem[]) {
  if (!import.meta.client) return
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch (e) {
    console.warn('continueWatching write failed', e)
  }
}

const state = ref<ContinueWatchingItem[]>([])
let bound = false

function bind() {
  if (bound || !import.meta.client) return
  bound = true
  state.value = read()
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) state.value = read()
  })
}

function key(id: number, type: ContinueWatchingItem['type'], season?: number, episode?: number) {
  return `${type}:${id}:${season ?? ''}:${episode ?? ''}`
}

export function useContinueWatching() {
  bind()

  let lastWriteAt = 0

  const upsert = (entry: Omit<ContinueWatchingItem, 'updatedAt'>) => {
    if (entry.position < ADD_AFTER_SECONDS) return
    if (entry.duration > 0 && entry.position / entry.duration >= COMPLETE_FRACTION) {
      return remove(entry.id, entry.type, entry.season, entry.episode)
    }
    const k = key(entry.id, entry.type, entry.season, entry.episode)
    const filtered = state.value.filter(
      (i) => key(i.id, i.type, i.season, i.episode) !== k,
    )
    state.value = [{ ...entry, updatedAt: Date.now() }, ...filtered].slice(0, MAX)
    // throttle persistence to ~5s — saves on rapid timeupdate events
    const now = Date.now()
    if (now - lastWriteAt > 5000) {
      write(state.value)
      lastWriteAt = now
    }
  }

  const flush = () => {
    write(state.value)
    lastWriteAt = Date.now()
  }

  const remove = (id: number, type: ContinueWatchingItem['type'], season?: number, episode?: number) => {
    const k = key(id, type, season, episode)
    state.value = state.value.filter(
      (i) => key(i.id, i.type, i.season, i.episode) !== k,
    )
    write(state.value)
  }

  const clear = () => {
    state.value = []
    write([])
  }

  const find = (id: number, type: ContinueWatchingItem['type'], season?: number, episode?: number) => {
    const k = key(id, type, season, episode)
    return state.value.find((i) => key(i.id, i.type, i.season, i.episode) === k)
  }

  return {
    items: readonly(state),
    upsert,
    flush,
    remove,
    clear,
    find,
  }
}
