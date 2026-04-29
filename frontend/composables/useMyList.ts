export type MyListItem = {
  id: number
  type: 'movie' | 'series'
  title: string
  poster: string | null
  year: number | null
  addedAt: number
}

const KEY = 'reelhouse:v1:myList'
const MAX = 100

function read(): MyListItem[] {
  if (!import.meta.client) return []
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as MyListItem[]) : []
  } catch {
    return []
  }
}

function write(list: MyListItem[]) {
  if (!import.meta.client) return
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)))
  } catch (e) {
    console.warn('myList write failed', e)
  }
}

const state = ref<MyListItem[]>([])
let bound = false

function bind() {
  if (bound || !import.meta.client) return
  bound = true
  state.value = read()
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) state.value = read()
  })
}

export function useMyList() {
  bind()

  const has = (id: number, type: MyListItem['type']) =>
    state.value.some((i) => i.id === id && i.type === type)

  const add = (item: Omit<MyListItem, 'addedAt'>) => {
    if (has(item.id, item.type)) return
    const next = [{ ...item, addedAt: Date.now() }, ...state.value].slice(0, MAX)
    state.value = next
    write(next)
  }

  const remove = (id: number, type: MyListItem['type']) => {
    const next = state.value.filter((i) => !(i.id === id && i.type === type))
    state.value = next
    write(next)
  }

  const toggle = (item: Omit<MyListItem, 'addedAt'>) =>
    has(item.id, item.type) ? remove(item.id, item.type) : add(item)

  const clear = () => {
    state.value = []
    write([])
  }

  const exportJson = () => JSON.stringify(state.value, null, 2)

  const importJson = (json: string) => {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) throw new Error('Expected an array')
    state.value = parsed.slice(0, MAX)
    write(state.value)
  }

  return {
    items: readonly(state),
    has,
    add,
    remove,
    toggle,
    clear,
    exportJson,
    importJson,
  }
}
