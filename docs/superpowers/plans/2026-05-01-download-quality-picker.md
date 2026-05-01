# Download Quality Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent "best-quality" download with a small popover that lists each available resolution and file size, so the user can pick.

**Architecture:** Backend `/api/stream/{movie,series}` enriches the existing `qualities` field from a list of resolution strings to a list of `{resolution, size_bytes, url}` objects. Frontend movie detail page replaces the direct-download button with a popover trigger; clicking a row triggers `<a download>` for that quality's URL. The Player overlay download chip and series detail page are not touched.

**Tech Stack:** FastAPI (Python 3.12) + Nuxt 3 (Vue 3 + TypeScript + Tailwind). No automated tests in repo — verification is via type-check, curl, and dev-server smoke test.

**Spec:** `docs/superpowers/specs/2026-05-01-download-quality-picker-design.md`

---

## File map

- **Modify** `backend/app/routes/stream.py` — change `qualities` value in `_resolve()` from `list[str]` to `list[dict]` carrying `resolution`, `size_bytes`, `url`
- **Modify** `frontend/composables/useStream.ts` — update the `StreamResolveResponse.qualities` TypeScript type
- **Modify** `frontend/pages/movie/[id].vue` — replace the direct-download click handler with a popover picker; add inline `formatBytes` helper

No new files.

---

## Task 1: Backend — return per-quality URL and size

**Files:**
- Modify: `backend/app/routes/stream.py:93-110`

- [ ] **Step 1: Replace the `qualities`-building block and the return statement**

Open `backend/app/routes/stream.py`. Replace lines 93-110 (the `# For series...` comment through the end of the `return {...}`) with:

```python
        # For series, restrict to the same (season, episode); else use all files.
        relevant = (
            [v for v in files.list if v.season == season and v.episode == episode]
            if season is not None and episode is not None
            else files.list
        )
        qualities = [
            {
                "resolution": f"{v.resolution}p",
                "size_bytes": v.size,
                "url": str(v.resource_link),
            }
            for v in relevant
            if v.resolution
        ]
        qualities.sort(key=lambda q: int(q["resolution"].rstrip("p")), reverse=True)

        return {
            "stream_url": str(chosen.resource_link),
            "qualities": qualities,
            "captions": captions,
            "source": "moviebox",
        }
```

Notes:
- `VideoFileMetadata` exposes `resolution: int`, `size: int` (bytes), `resource_link: HttpUrl` — confirmed in `moviebox-api-main/src/moviebox_api/v3/models/downloadables.py:16-39`.
- `stream_url` is preserved exactly so the Player and the in-overlay download chip keep working.
- Multiple files may exist at the same resolution — keep all of them (don't dedupe). Sorting is stable, so the original order within a resolution is retained.

- [ ] **Step 2: Start the backend dev server**

Run from the repo root:

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

Leave it running in another terminal. If `app.main:app` is wrong, look at `backend/app/` for the actual entrypoint.

- [ ] **Step 3: Hit the movie endpoint and verify the new shape**

Pick any TMDB movie ID known to be available (e.g., `tt0816692` Interstellar = TMDB 157336):

```bash
curl -s "http://localhost:8000/api/stream/movie?tmdb_id=157336&title=Interstellar&year=2014" | python -m json.tool
```

Expected: top-level `stream_url`, `captions`, `source` unchanged. `qualities` is now an array of objects:

```json
"qualities": [
  { "resolution": "1080p", "size_bytes": 1234567890, "url": "https://..." },
  { "resolution": "720p",  "size_bytes":  600000000, "url": "https://..." }
]
```

Verify: array is sorted high→low, every entry has all three keys, `size_bytes` is a positive integer, `url` is a string starting with `http`.

- [ ] **Step 4: Hit the series endpoint and verify the per-episode filter still works**

```bash
curl -s "http://localhost:8000/api/stream/series?tmdb_id=1399&title=Game%20of%20Thrones&season=1&episode=1" | python -m json.tool
```

Expected: same shape. Every `qualities[i].url` should belong to S01E01 only (eyeball the URLs — moviebox URLs typically include episode hints, but the key check is that the count is reasonable for one episode, not the whole series).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/stream.py
git commit -m "backend: include per-quality url and size in stream response"
```

---

## Task 2: Frontend — update the TypeScript type

**Files:**
- Modify: `frontend/composables/useStream.ts:3-8`

- [ ] **Step 1: Replace the `StreamResolveResponse` interface**

Open `frontend/composables/useStream.ts`. Replace lines 3-8:

```ts
export interface StreamOption {
  resolution: string
  size_bytes: number
  url: string
}

export interface StreamResolveResponse {
  stream_url: string
  qualities: StreamOption[]
  captions: Array<{ lang: string; url: string }>
  source: string
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes. If errors mention `qualities` being used as `string[]` somewhere we missed, grep for `qualities` under `frontend/` and fix the call site — the spec only expects the type to be consumed in the picker we're about to build.

- [ ] **Step 3: Commit**

```bash
git add frontend/composables/useStream.ts
git commit -m "frontend: type qualities as StreamOption objects"
```

---

## Task 3: Frontend — quality picker popover on movie detail page

**Files:**
- Modify: `frontend/pages/movie/[id].vue:64-97` (script: replace download state + handler)
- Modify: `frontend/pages/movie/[id].vue:137-152` (template: replace download button + error line)

- [ ] **Step 1: Replace the script-block download logic**

Open `frontend/pages/movie/[id].vue`. Replace lines 64-97 (the block from `const { public: { apiBase } } = useRuntimeConfig()` through the closing brace of `downloadMovie`) with:

```ts
import type { StreamOption, StreamResolveResponse } from '~/composables/useStream'

const { public: { apiBase } } = useRuntimeConfig()
const pickerOpen = ref(false)
const pickerLoading = ref(false)
const pickerError = ref<string | null>(null)
const qualities = ref<StreamOption[]>([])
const downloadButton = ref<HTMLButtonElement | null>(null)
const pickerEl = ref<HTMLDivElement | null>(null)

const formatBytes = (n: number) => {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`
  return `${(n / 1e3).toFixed(0)} KB`
}

const fetchQualities = async () => {
  if (!movie.value) return
  pickerLoading.value = true
  pickerError.value = null
  try {
    const params = new URLSearchParams({
      tmdb_id: String(movie.value.id),
      title: movie.value.title,
    })
    if (year.value) params.set('year', year.value)
    const res = await $fetch<StreamResolveResponse>(
      `${apiBase}/api/stream/movie?${params.toString()}`,
    )
    if (!res?.qualities?.length) throw new Error('no qualities')
    qualities.value = res.qualities
  } catch (e: any) {
    const status = e?.response?.status ?? e?.statusCode
    pickerError.value =
      status === 404 ? 'Not available from source.' : 'Download failed.'
  } finally {
    pickerLoading.value = false
  }
}

const togglePicker = async () => {
  if (pickerOpen.value) {
    pickerOpen.value = false
    return
  }
  pickerOpen.value = true
  if (!qualities.value.length && !pickerError.value) {
    await fetchQualities()
  }
}

const downloadOption = (opt: StreamOption) => {
  if (!movie.value) return
  const safe = movie.value.title.replace(/[\\/:*?"<>|]+/g, ' ').trim()
  const a = document.createElement('a')
  a.href = opt.url
  a.download = `${safe}.mp4`
  a.target = '_blank'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  pickerOpen.value = false
}

const onDocClick = (e: MouseEvent) => {
  if (!pickerOpen.value) return
  const t = e.target as Node
  if (pickerEl.value?.contains(t) || downloadButton.value?.contains(t)) return
  pickerOpen.value = false
}
const onKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') pickerOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
```

What changed vs. the old `downloadMovie`:
- Removed `downloading` and `downloadError` refs (replaced by `pickerLoading` / `pickerError`)
- Removed the direct-download path; downloading now happens per-row via `downloadOption`
- Added popover open/close state, outside-click + Escape close
- Caches `qualities` in a ref — second open of the popover doesn't re-fetch

- [ ] **Step 2: Replace the template Download button + error line**

Still in `frontend/pages/movie/[id].vue`. Find the `<div class="flex flex-wrap gap-3 pt-2">` block currently at lines 137-149 and the `<div v-if="downloadError" ...>` at lines 150-152. Replace the entire range (lines 137-152) with:

```vue
            <div class="flex flex-wrap gap-3 pt-2">
              <NuxtLink :to="`/watch/movie/${movie.id}`" class="btn-primary">▶ Play</NuxtLink>
              <div class="relative">
                <button
                  ref="downloadButton"
                  class="btn-ghost"
                  :aria-expanded="pickerOpen"
                  aria-haspopup="menu"
                  @click="togglePicker"
                >
                  ⬇ Download
                </button>
                <div
                  v-if="pickerOpen"
                  ref="pickerEl"
                  role="menu"
                  class="absolute z-20 mt-2 right-0 min-w-[14rem] bg-ink-900
                         ring-1 ring-white/10 rounded-lg shadow-xl p-1"
                >
                  <div
                    v-if="pickerLoading"
                    class="px-3 py-2 text-sm text-slate-400"
                  >
                    Loading qualities…
                  </div>
                  <div
                    v-else-if="pickerError"
                    class="px-3 py-2 text-sm text-red-400"
                  >
                    {{ pickerError }}
                  </div>
                  <button
                    v-for="q in qualities"
                    v-else
                    :key="q.url"
                    role="menuitem"
                    class="w-full flex items-center justify-between gap-4 px-3 py-2
                           rounded-md text-sm hover:bg-white/5"
                    @click="downloadOption(q)"
                  >
                    <span class="font-medium">{{ q.resolution }}</span>
                    <span class="text-slate-400">{{ formatBytes(q.size_bytes) }}</span>
                  </button>
                </div>
              </div>
              <button class="btn-ghost" @click="toggleList">
                {{ inList ? '✓ In My List' : '+ My List' }}
              </button>
            </div>
```

Notes:
- The old standalone `<div v-if="downloadError">` line below the button row is removed — errors now show inside the popover.
- `right-0` aligns the popover's right edge with the button's right edge so it doesn't overflow on the right.
- `z-20` puts it above the hero overlay (`bg-hero-fade` is below z-10 by default).
- `ref="downloadButton"` and `ref="pickerEl"` match the script refs and let outside-click detection ignore clicks on either.

- [ ] **Step 3: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 4: Manual smoke test — happy path**

Start the frontend dev server (backend from Task 1 should still be running):

```bash
cd frontend && npm run dev
```

In a browser, open `http://localhost:3000/movie/157336` (Interstellar — or any movie you know moviebox carries).

Verify each item:
1. Click "⬇ Download". Popover opens, shows "Loading qualities…" briefly.
2. Popover then shows multiple rows like `1080p · 1.20 GB`, sorted high→low.
3. Click a row. The browser prompts to download / starts downloading. Filename is `Interstellar.mp4` (no resolution suffix). Popover closes.
4. Click the Download button again. Popover reopens **instantly** (no spinner) — qualities are cached. Click outside the popover — it closes.
5. Reopen, then press `Escape` — it closes.

- [ ] **Step 5: Manual smoke test — error path**

Open a movie that moviebox doesn't carry (try a very obscure or just-released title — or hand-edit the URL with a fake TMDB id like `/movie/999999999`).

Verify:
1. Click "⬇ Download". Popover opens, then shows "Not available from source." in red.
2. Popover does not crash; outside-click and Escape still close it.

- [ ] **Step 6: Regression check — Player overlay download still works**

Open `http://localhost:3000/watch/movie/157336`. Wait for the player to resolve. Click the small "⬇ Download" chip in the top-right. It should still trigger a single download (highest quality) — no popover, exactly the old behavior. This confirms the backend's `stream_url` field is preserved.

- [ ] **Step 7: Commit**

```bash
git add frontend/pages/movie/[id].vue
git commit -m "frontend: quality picker popover on movie download button"
```

---

## Self-review

**Spec coverage:**
- Backend response shape change → Task 1 ✓
- Frontend type update → Task 2 ✓
- Popover anchored below button, right-aligned → Task 3 Step 2 (`right-0 mt-2`) ✓
- Loading / error / open states → Task 3 Step 1 + 2 ✓
- Outside-click + Escape close → Task 3 Step 1 ✓
- Cache resolved response per page-load → Task 3 Step 1 (`qualities` ref + guard in `togglePicker`) ✓
- Single-quality case still shows popover → Task 3 Step 1: `v-for` on `qualities` renders even one row; `togglePicker` doesn't auto-click ✓
- Sanitized filename, no resolution suffix → Task 3 Step 1 (`safe.replace(...)`, `${safe}.mp4`) ✓
- `formatBytes` helper inline → Task 3 Step 1 ✓
- Player overlay chip and series detail page untouched → not edited; Task 3 Step 6 verifies player still works ✓

**Placeholder scan:** none.

**Type consistency:** `StreamOption` defined in Task 2 is imported and used in Task 3. Field names (`resolution`, `size_bytes`, `url`) match Task 1's backend output exactly.
