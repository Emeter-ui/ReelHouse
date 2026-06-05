// A true "watch history" log: every title you press play on is recorded
// immediately and KEPT — even after you finish it. This is distinct from
// useContinueWatching, which drops sub-30s plays and removes finished items
// (correct for a "resume" row, wrong for a history log).

export type WatchHistoryItem = {
  id: number
  type: 'movie' | 'series'
  title: string
  poster: string | null
  season?: number
  episode?: number
  position: number    // last known seconds
  duration: number    // seconds
  completed: boolean
  watchedAt: number   // last time it was played (ms epoch)
}

const KEY = 'reelhouse:v1:watchHistory'
const MAX = 200
const COMPLETE_FRACTION = 0.95

function read(): WatchHistoryItem[] {
  if (!import.meta.client) return []
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as WatchHistoryItem[]) : []
  } catch {
    return []
  }
}

function write(list: WatchHistoryItem[]) {
  if (!import.meta.client) return
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch (e) {
    console.warn('watchHistory write failed', e)
  }
}

const state = ref<WatchHistoryItem[]>([])
let bound = false

function bind() {
  if (bound || !import.meta.client) return
  bound = true
  state.value = read()
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) state.value = read()
  })
}

function key(id: number, type: WatchHistoryItem['type'], season?: number, episode?: number) {
  return `${type}:${id}:${season ?? ''}:${episode ?? ''}`
}

export function useWatchHistory() {
  bind()

  let lastWriteAt = 0

  // Record (or refresh) a play. Called the moment playback starts and again
  // on progress updates. Always moves the entry to the front (most recent).
  const record = (entry: Omit<WatchHistoryItem, 'watchedAt' | 'completed'>) => {
    const k = key(entry.id, entry.type, entry.season, entry.episode)
    const existing = state.value.find(
      (i) => key(i.id, i.type, i.season, i.episode) === k,
    )
    const duration = entry.duration || existing?.duration || 0
    const position = entry.position || existing?.position || 0
    const completed =
      (duration > 0 && position / duration >= COMPLETE_FRACTION) ||
      existing?.completed ||
      false
    const merged: WatchHistoryItem = {
      ...entry,
      position,
      duration,
      completed,
      watchedAt: Date.now(),
    }
    const filtered = state.value.filter(
      (i) => key(i.id, i.type, i.season, i.episode) !== k,
    )
    state.value = [merged, ...filtered].slice(0, MAX)
    // throttle persistence — progress events fire several times a second
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

  const remove = (id: number, type: WatchHistoryItem['type'], season?: number, episode?: number) => {
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

  return {
    items: readonly(state),
    record,
    flush,
    remove,
    clear,
  }
}
