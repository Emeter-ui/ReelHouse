# Download Quality Picker — Design

**Date:** 2026-05-01
**Status:** Approved
**Scope:** Movie detail page only (`/movie/[id]`). Series detail page has no Download button today and is out of scope. Player overlay download chip is unchanged.

## Goal

When a user clicks the "⬇ Download" button on a movie detail page, show a small popover listing each available video resolution with its file size. Clicking a row downloads that specific resolution.

## Motivation

Today, the Download button silently picks the highest available resolution. This is wasteful (1080p of a movie can be ~2 GB) and gives the user no choice. The underlying moviebox API exposes multiple resolutions per title with file sizes; the frontend should surface that.

## Current behavior

- `GET /api/stream/movie?tmdb_id=…` returns `{ stream_url, qualities: ["1080p", ...], captions, source }`. `stream_url` is the URL of the highest-resolution file only; `qualities` is a list of resolution strings with no per-quality URL or size.
- Movie page (`frontend/pages/movie/[id].vue`): clicking Download calls the endpoint, takes the single `stream_url`, and triggers `<a download>`.

## New backend response shape

`/api/stream/movie` and `/api/stream/series` will return:

```json
{
  "stream_url": "https://…",          // unchanged: highest resolution, used by Player
  "qualities": [
    { "resolution": "1080p", "size_bytes": 1287654321, "url": "https://…" },
    { "resolution": "720p",  "size_bytes":  734003200, "url": "https://…" },
    { "resolution": "480p",  "size_bytes":  419430400, "url": "https://…" }
  ],
  "captions": [...],
  "source": "moviebox"
}
```

- Sorted high → low by resolution.
- For series, only entries matching the requested `(season, episode)` are included (matches existing filter in `_pick_best_video`).
- `stream_url` stays for backward compatibility with the player; it equals `qualities[0].url`.

This is a single edit in `_resolve()` in `backend/app/routes/stream.py`. `VideoFileMetadata` already exposes `resolution: int`, `size: int` (bytes), and `resource_link: HttpUrl`.

## Frontend behavior — `pages/movie/[id].vue`

The Download button becomes a popover trigger.

**States**

| State          | Trigger                                  | Display                                            |
|----------------|------------------------------------------|----------------------------------------------------|
| Idle           | Initial                                  | "⬇ Download" button                                |
| Loading        | User clicked, fetch in flight            | Popover open with "Loading qualities…"             |
| Open           | Fetch resolved with ≥1 quality           | Popover with rows: `1080p · 1.20 GB`               |
| Error / 404    | Fetch failed or no qualities             | Popover with "Not available from source." (404) or "Download failed." (other) |

**Popover anchoring:** absolutely positioned below the Download button, right-aligned to it. Above other content (`z-index` above hero). Width auto, min ~12rem. Style: `bg-ink-900 ring-1 ring-white/10 rounded-lg shadow-xl p-1`.

**Rows:** each row is a `<button>` with `resolution` (left, font-medium) and humanized size (right, slate-400). Hover: `bg-white/5`. Click: trigger download via the same `<a download>` mechanism in use today (sanitized filename `<title>.mp4`), then close the popover.

**Closing:**
- Click outside (window click handler that ignores clicks inside the popover/button)
- `Escape` key
- After a row is clicked

**Caching:** the resolved response is fetched on first open per-page-load and cached in a local ref. Subsequent opens are instant. Re-opening after an error retries.

**Single-quality case:** still show the popover with one row. Keeps UX consistent and lets the user see the file size before committing. Not auto-clicked.

## Filename

Same sanitization as today: `title.replace(/[\\/:*?"<>|]+/g, ' ').trim()` + `.mp4`. Resolution is not appended to the filename (keeps it clean; user knows what they picked).

## Size formatting

`formatBytes(n)`:
- `n >= 1e9` → `${(n/1e9).toFixed(2)} GB`
- `n >= 1e6` → `${(n/1e6).toFixed(0)} MB`
- else → `${(n/1e3).toFixed(0)} KB`

Inline helper, not a shared composable (only one call site).

## Out of scope

- Adding a Download button to series detail page (no current button to extend; episode downloads happen via the in-player chip)
- Modifying the in-player Download chip (`components/Player.vue`) — stays single-click, highest quality
- Resolution preference / remembering the last choice
- Showing codec, bitrate, or duration in the picker
- Subtitle download picker

## Files touched

- `backend/app/routes/stream.py` — extend `_resolve()` to include per-quality `{resolution, size_bytes, url}` array
- `frontend/composables/useStream.ts` — update `StreamResolveResponse.qualities` type from `string[]` to `Array<{ resolution: string; size_bytes: number; url: string }>`
- `frontend/pages/movie/[id].vue` — replace direct download with picker popover

## Risk

Low. Backend change is additive (new field structure inside `qualities`); the existing player consumer reads `stream_url` only, which is preserved. Frontend change is contained to one page.
