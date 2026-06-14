<script setup lang="ts">
import videojs from 'video.js'
import 'video.js/dist/video-js.css'
// video.js 8 ships @videojs/http-streaming (VHS), which plays DASH out of the
// box — we just pass `type: 'application/dash+xml'` and it parses the .mpd
// itself. (We tried videojs-contrib-dash first; that package is pinned to
// dash.js 4 + video.js 5–7 and silently no-ops on this stack.)
import {
  canFetchDirect,
  captionsUrl,
  proxiedUrl,
  dashManifestUrl,
  isPlayableCodec,
  streamHeight,
  pickConnectionAwareResolution,
  type StreamResolveResponse,
  type StreamOption,
} from '~/composables/useStream'
import { useContinueWatching } from '~/composables/useContinueWatching'
import { useWatchHistory } from '~/composables/useWatchHistory'

type VjsPlayer = ReturnType<typeof videojs>

type Props = {
  resolved: StreamResolveResponse | null
  pending: boolean
  error: unknown
  /** Identity for Continue Watching */
  contentId: number
  contentType: 'movie' | 'series'
  contentTitle: string
  contentPoster: string | null
  season?: number
  episode?: number
  /** Resolution string like "1080p" — picks the matching entry in resolved.qualities. */
  preferredResolution?: string
}
const props = defineProps<Props>()

const cw = useContinueWatching()
const wh = useWatchHistory()
const videoElement = ref<HTMLVideoElement | null>(null)
const finalSrc = ref<string | null>(null)
const probeStatus = ref<'idle' | 'probing' | 'direct' | 'proxied' | 'failed'>('idle')
const { public: { apiBase } } = useRuntimeConfig()
const isProdLocalhost = computed(() => {
  if (process.server) return false
  const isProd = window.location.hostname !== 'localhost'
  return isProd && apiBase.includes('localhost')
})
const videoError = ref<string | null>(null)
let player: VjsPlayer | null = null
let remoteTracks: HTMLTrackElement[] = []
const reloadPage = () => location.reload()

// --- Quality selection -------------------------------------------------------
// Streams are progressive MP4 (no HLS/ABR), so we do the switching ourselves:
// pick a connection-aware default, let the viewer override, and step down
// automatically when the network stalls. The downgrade ladder is limited to
// browser-playable (H.264) rungs — auto-switching into an HEVC rung would just
// black-screen on engines without HEVC decode.
const allQualities = computed<StreamOption[]>(() =>
  [...(props.resolved?.qualities ?? [])].sort(
    (a, b) => streamHeight(b.resolution) - streamHeight(a.resolution),
  ),
)
const isDashStream = (q: StreamOption) => (q.format ?? '').toLowerCase() === 'dash'
const ladder = computed(() =>
  allQualities.value.filter((q) => isPlayableCodec(q.codec, { isDash: isDashStream(q) })),
)
// Auto-downgrade stays inside progressive MP4 — re-bootstrapping dash.js
// mid-playback on a stalling network would thrash worse than the original
// stall, and the MP4 ladder is always present when DASH is.
const autoDowngradeLadder = computed(() => ladder.value.filter((q) => !isDashStream(q)))
const riskyQualities = computed(() =>
  allQualities.value.filter((q) => !isPlayableCodec(q.codec, { isDash: isDashStream(q) })),
)

// 'auto' = connection default + auto-downgrade; 'pinned' = a viewer-chosen rung.
const mode = ref<'auto' | 'pinned'>('auto')
const autoResolution = ref<string | null>(null)
const pinnedResolution = ref<string | null>(null)
// Position to restore after a quality swap reloads the <video> source.
let pendingSeek: number | null = null

const currentResolution = computed(() =>
  mode.value === 'pinned' ? pinnedResolution.value : autoResolution.value,
)

// (Re)derive the auto default whenever the ladder changes (new title/episode).
// A preferredResolution prop (URL ?q=) pins that rung up front if it exists.
// `pinnedResolution` can be any pickable rung (incl. DASH); the auto default
// stays inside the progressive MP4 pool to avoid surprising auto-downgrades
// into DASH-HEVC on Firefox (where canPlayHevcMse is false anyway).
watch(
  [ladder, autoDowngradeLadder],
  ([pickable, autoPool]) => {
    if (!pickable.length) {
      autoResolution.value = null
      return
    }
    const wanted = props.preferredResolution
    if (wanted && pickable.some((q) => q.resolution === wanted)) {
      mode.value = 'pinned'
      pinnedResolution.value = wanted
    }
    const pool = autoPool.length ? autoPool : pickable
    if (!autoResolution.value || !pool.some((q) => q.resolution === autoResolution.value)) {
      autoResolution.value = pickConnectionAwareResolution(pool)
    }
  },
  { immediate: true },
)

// Picks from the full list (incl. HEVC) so a manual pin can select any rung,
// but the auto default/downgrade only ever names rungs from `ladder`.
const activeQuality = computed(() => {
  const res = currentResolution.value
  return (res && allQualities.value.find((q) => q.resolution === res)) || null
})
const activeStreamUrl = computed(
  () => activeQuality.value?.url ?? props.resolved?.stream_url ?? null,
)

// --- Quality picker UI + auto-downgrade -------------------------------------
const showQualityMenu = ref(false)
const downgradeNotice = ref<string | null>(null)
let downgradeNoticeTimer: ReturnType<typeof setTimeout> | null = null
let stallTimer: ReturnType<typeof setTimeout> | null = null
let recentStalls: number[] = []
const STALL_TIMEOUT_MS = 6000

const qualityLabel = computed(() => {
  if (mode.value === 'pinned') return pinnedResolution.value ?? '—'
  return autoResolution.value ? `Auto · ${autoResolution.value}` : 'Auto'
})

const prettySize = (bytes?: number) => {
  if (!bytes) return ''
  const gb = bytes / 1e9
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`
}

const clearStallTimer = () => {
  if (stallTimer) {
    clearTimeout(stallTimer)
    stallTimer = null
  }
}

const flashNotice = (msg: string) => {
  downgradeNotice.value = msg
  if (downgradeNoticeTimer) clearTimeout(downgradeNoticeTimer)
  downgradeNoticeTimer = setTimeout(() => {
    downgradeNotice.value = null
  }, 4000)
}

// Step down one playable rung. No-op when paused at the lowest rung or when the
// viewer has pinned a quality (their choice wins over auto-downgrade).
const autoDowngrade = () => {
  if (mode.value !== 'auto') return
  clearStallTimer()
  const list = autoDowngradeLadder.value
  const idx = list.findIndex((q) => q.resolution === autoResolution.value)
  if (idx === -1 || idx >= list.length - 1) return
  const next = list[idx + 1]
  if (player) pendingSeek = player.currentTime() ?? 0
  autoResolution.value = next.resolution
  recentStalls = []
  flashNotice(`Slow network — switched to ${next.resolution}`)
}

const selectQuality = (resolution: string) => {
  if (player) pendingSeek = player.currentTime() ?? 0
  mode.value = 'pinned'
  pinnedResolution.value = resolution
  showQualityMenu.value = false
}

const selectAuto = () => {
  if (player) pendingSeek = player.currentTime() ?? 0
  mode.value = 'auto'
  if (!autoResolution.value || !ladder.value.some((q) => q.resolution === autoResolution.value)) {
    autoResolution.value = pickConnectionAwareResolution(ladder.value)
  }
  showQualityMenu.value = false
}

const sourceType = computed(() => {
  const q = activeQuality.value
  if (q?.format === 'dash') return 'application/dash+xml'
  const u = (activeStreamUrl.value ?? '').toLowerCase()
  if (u.includes('.m3u8')) return 'application/x-mpegURL'
  if (u.endsWith('.mpd') || u.includes('.mpd?')) return 'application/dash+xml'
  return 'video/mp4'
})

// MovieBox returns captions in arbitrary order — English is rarely first.
const defaultCaptionUrl = computed(() => {
  const list = props.resolved?.captions ?? []
  return list.find((c) => c.lang?.toLowerCase().startsWith('en'))?.url ?? null
})

// `<track srclang>` requires a valid BCP 47 tag. MovieBox sometimes labels
// captions in their own scripts ("اَلْعَرَبِيَّةُ"); the slice would be non-ASCII
// and rejected by browsers. Fall back to "und".
const toSrcLang = (lang: string): string => {
  const slug = (lang || '').slice(0, 2).toLowerCase()
  return /^[a-z]{2}$/.test(slug) ? slug : 'und'
}

watch(
  activeStreamUrl,
  async (url) => {
    if (!url) {
      finalSrc.value = null
      return
    }
    probeStatus.value = 'probing'
    // DASH manifests sit behind CloudFront signed cookies that the browser
    // can't apply cross-origin from JS — always go through the dedicated
    // manifest endpoint, which fetches the .mpd with the signed cookie and
    // injects a <BaseURL> so segments resolve to absolute CDN URLs.
    const q = activeQuality.value
    if (q?.format === 'dash') {
      finalSrc.value = dashManifestUrl(url, props.resolved?.play_referer, q.sign_cookie)
      probeStatus.value = 'proxied'
      return
    }
    const direct = await canFetchDirect(url)
    if (direct) {
      finalSrc.value = url
      probeStatus.value = 'direct'
    } else {
      finalSrc.value = proxiedUrl(url, props.resolved?.play_referer)
      probeStatus.value = 'proxied'
    }
  },
  { immediate: true },
)

const previous = computed(() =>
  cw.find(props.contentId, props.contentType, props.season, props.episode),
)
let cwRestored = false

const identity = () => ({
  id: props.contentId,
  type: props.contentType,
  title: props.contentTitle,
  poster: props.contentPoster,
  season: props.season,
  episode: props.episode,
})

const upsertProgress = () => {
  if (!player) return
  const cur = player.currentTime() ?? 0
  const dur = player.duration() ?? 0
  if (!dur || isNaN(dur)) return
  cw.upsert({
    ...identity(),
    position: Math.floor(cur),
    duration: Math.floor(dur),
  })
  // Watch History keeps a permanent log of progress (incl. finished titles).
  wh.record({
    ...identity(),
    position: Math.floor(cur),
    duration: Math.floor(dur),
  })
}

// Log the title in Watch History the instant playback begins, so it shows up
// even if the viewer only watches a few seconds.
const recordHistoryStart = () => {
  if (!player) return
  wh.record({
    ...identity(),
    position: Math.floor(player.currentTime() ?? 0),
    duration: Math.floor(player.duration() || 0),
  })
}

// Re-add captions to the player. Remote tracks added with manualCleanup=true
// persist across source changes, so we remove them explicitly when the
// captions list changes (e.g. when navigating to a different episode).
const syncCaptions = () => {
  if (!player) return
  for (const el of remoteTracks) player.removeRemoteTextTrack(el)
  remoteTracks = []
  const captions = props.resolved?.captions ?? []
  const defaultUrl = defaultCaptionUrl.value
  for (const c of captions) {
    const trackEl = player.addRemoteTextTrack(
      {
        kind: 'subtitles',
        label: c.lang,
        srclang: toSrcLang(c.lang),
        src: captionsUrl(c.url),
        default: c.url === defaultUrl,
      },
      true,
    )
    if (trackEl) remoteTracks.push(trackEl as unknown as HTMLTrackElement)
  }
}

// VHS exposes `representations()` on its tech object: each entry is a
// playable rendition with a `.enabled(bool)` switch. Enabling only the one
// at `height` pins the chosen rung — VHS's ABR honours `enabled` and won't
// drift away from the viewer's pick.
const lockDashHeight = (height: number) => {
  const tryLock = (): boolean => {
    const tech: any = (player as any)?.tech?.(true)
    const reps = tech?.vhs?.representations?.()
    if (!reps || !reps.length) return false
    let matched = false
    reps.forEach((r: any) => {
      const enable = r.height === height
      if (enable) matched = true
      try { r.enabled?.(enable) } catch { /* some reps may be audio-only */ }
    })
    return matched
  }
  if (tryLock()) return
  // Reps appear after VHS parses the manifest; loadedmetadata is the
  // earliest reliable hook.
  const onReady = () => {
    tryLock()
    player?.off('loadedmetadata', onReady)
  }
  player?.on('loadedmetadata', onReady)
}

// VHS issues every manifest + segment fetch through `videojs.Vhs.xhr`. Its
// `beforeRequest` is global (not per-player), so we install it once and
// gate behaviour on a module-scoped DASH context. When `_dashContext` is
// null the hook is a no-op, leaving non-DASH playback untouched.
let _dashContext: { cookie: string; referer?: string } | null = null
let _vhsHookInstalled = false
const installVhsRewriteHook = () => {
  if (_vhsHookInstalled) return
  const Vhs = (videojs as any).Vhs
  if (!Vhs?.xhr) return
  _vhsHookInstalled = true
  Vhs.xhr.beforeRequest = (options: any) => {
    if (!_dashContext) return options
    const url: string = options?.uri || ''
    // Skip URLs that already point at our proxy / manifest endpoint.
    if (url.includes('/api/proxy?') || url.includes('/api/dash-manifest?')) return options
    if (/^https?:\/\//.test(url)) {
      options.uri = proxiedUrl(url, _dashContext.referer, undefined, _dashContext.cookie)
    }
    return options
  }
}

const applySource = () => {
  if (!player || !finalSrc.value) return
  videoError.value = null
  // For DASH, set the rewrite context + install the hook BEFORE player.src()
  // so the first segment fetches that VHS kicks off after parsing the
  // manifest already see the proxy-rewriting hook.
  if (sourceType.value === 'application/dash+xml') {
    const q = activeQuality.value
    _dashContext = q?.sign_cookie
      ? { cookie: q.sign_cookie, referer: props.resolved?.play_referer }
      : null
    installVhsRewriteHook()
  } else {
    _dashContext = null
  }
  player.src({ src: finalSrc.value, type: sourceType.value })
  player.play()?.catch(() => {
    /* autoplay-blocked is fine; user can click play */
  })
  if (sourceType.value === 'application/dash+xml') {
    const target = activeQuality.value?.target_height
    if (target) lockDashHeight(target)
  }
}

const initPlayer = () => {
  if (player || !videoElement.value) return
  player = videojs(videoElement.value, {
    controls: true,
    preload: 'auto',
    fluid: false,
    fill: true,
    responsive: true,
    playsinline: true,
    crossOrigin: 'anonymous',
    poster: props.contentPoster ?? undefined,
    controlBar: {
      pictureInPictureToggle: true,
      remainingTimeDisplay: true,
      subsCapsButton: true,
    },
    html5: {
      vhs: { 
        // On iOS and Safari, native HLS support is more reliable than VHS.
        overrideNative: !videojs.browser.IS_SAFARI && !videojs.browser.IS_IOS 
      },
    },
  })

  player.on('loadedmetadata', () => {
    // A quality swap captured the playhead — restore it before anything else.
    if (pendingSeek != null && player) {
      player.currentTime(pendingSeek)
      pendingSeek = null
      return
    }
    if (cwRestored) return
    if (previous.value && player) {
      player.currentTime(previous.value.position)
    }
    cwRestored = true
  })

  player.on('timeupdate', upsertProgress)
  player.on('play', recordHistoryStart)

  // Auto-downgrade on a struggling network (auto mode only). A sustained stall
  // (still waiting after STALL_TIMEOUT_MS) or frequent re-buffering (3 stalls
  // within 30s) steps down one playable rung.
  player.on('waiting', () => {
    if (mode.value !== 'auto') return
    clearStallTimer()
    stallTimer = setTimeout(autoDowngrade, STALL_TIMEOUT_MS)
    const now = Date.now()
    recentStalls = recentStalls.filter((t) => now - t < 30000)
    recentStalls.push(now)
    if (recentStalls.length >= 3) autoDowngrade()
  })
  player.on('playing', clearStallTimer)
  player.on('canplaythrough', clearStallTimer)

  // On mobile, force landscape while the video is fullscreen and restore the
  // natural orientation on exit. Uses the Screen Orientation API, which only
  // works while a fullscreen element is active; iOS Safari lacks lock(), so
  // the optional-chaining makes this a no-op there.
  player.on('fullscreenchange', () => {
    const orientation = screen.orientation as ScreenOrientation & {
      lock?: (o: 'portrait' | 'landscape') => Promise<void>
    }
    if (!orientation?.lock) return
    if (player?.isFullscreen()) {
      orientation.lock('landscape').catch(() => {
        /* rejected on desktop / unsupported — ignore */
      })
    } else {
      orientation.unlock?.()
    }
  })

  player.on('error', () => {
    const err = player?.error()
    const codeMap: Record<number, string> = {
      1: 'aborted',
      2: 'network error',
      3: 'decode error (codec not supported by your browser — likely HEVC/H.265)',
      4: 'source not supported',
    }
    videoError.value = err
      ? codeMap[err.code] || `error code ${err.code}`
      : 'Playback error'
    probeStatus.value = 'failed'
  })

  // First source + captions if already resolved by the time we mount.
  if (finalSrc.value) applySource()
  syncCaptions()
}

watch(finalSrc, applySource)
watch(
  [() => props.resolved?.captions, defaultCaptionUrl],
  syncCaptions,
)

const handleKeyDown = (e: KeyboardEvent) => {
  if (!player) return
  
  // Don't trigger if user is typing in an input field or focusing a button
  const target = e.target as HTMLElement
  if (target && ['INPUT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)) return

  if (e.key === 'ArrowRight') {
    player.currentTime((player.currentTime() || 0) + 10)
    e.preventDefault()
  } else if (e.key === 'ArrowLeft') {
    player.currentTime((player.currentTime() || 0) - 10)
    e.preventDefault()
  } else if (e.key === ' ' || e.code === 'Space') {
    if (player.paused()) {
      player.play()?.catch(() => {})
    } else {
      player.pause()
    }
    e.preventDefault()
  } else if (e.key === 'f' || e.key === 'F') {
    if (player.isFullscreen()) {
      player.exitFullscreen()
    } else {
      player.requestFullscreen()
    }
    e.preventDefault()
  }
}

onMounted(() => {
  initPlayer()
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  cw.flush()
  wh.flush()
  clearStallTimer()
  if (downgradeNoticeTimer) clearTimeout(downgradeNoticeTimer)
  // Release any landscape lock so non-player pages rotate freely again.
  ;(screen.orientation as ScreenOrientation & { unlock?: () => void })?.unlock?.()
  if (player) {
    player.dispose()
    player = null
  }
})
</script>

<template>
  <div class="relative w-full aspect-video bg-black rounded-lg overflow-hidden group">
    <!-- Overlay: Loading -->
    <div v-if="pending" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Resolving stream…</span>
      </div>
    </div>

    <!-- Overlay: Probing -->
    <div v-else-if="probeStatus === 'probing'" class="absolute inset-0 flex items-center justify-center text-slate-400 z-20 pointer-events-none">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin" />
        <span class="text-sm font-medium tracking-wide">Connecting to source…</span>
      </div>
    </div>

    <!-- Overlay: Error / Unavailable -->
    <div
      v-else-if="error || !resolved || !activeStreamUrl"
      class="absolute inset-0 flex items-center justify-center px-6 text-center text-slate-300 z-20 bg-black/40 backdrop-blur-sm"
    >
      <div class="max-w-xs space-y-4">
        <div class="space-y-2">
          <p class="font-semibold text-red-400 flex items-center justify-center gap-2">
            <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            {{ error ? 'Connection Error' : (!resolved || !activeStreamUrl ? 'Source Unavailable' : 'Error') }}
          </p>
          <p class="text-sm text-slate-400 leading-relaxed">
            <template v-if="isProdLocalhost">
              Frontend is trying to reach localhost:8003 from a production site. Please set NUXT_PUBLIC_API_BASE in Netlify settings.
            </template>
            <template v-else-if="error">
              Could not reach the backend server. The request may have timed out or the server is offline.
            </template>
            <template v-else>
              This title is currently unavailable for streaming. It may be coming soon or restricted in your region.
            </template>
          </p>
        </div>
        <button
          class="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/10 rounded-full text-xs font-medium transition-colors"
          @click="reloadPage"
        >
          Try Again
        </button>
      </div>
    </div>

    <!-- video.js mounts inside this <video> element. crossOrigin propagates
         to <track> requests so VTT subtitles load over CORS. -->
    <div v-show="finalSrc" class="absolute inset-0 w-full h-full">
      <video
        ref="videoElement"
        class="video-js vjs-default-skin vjs-big-play-centered w-full h-full"
        playsinline
      />
    </div>

    <!-- UI Overlays (Chips) -->
    <div class="absolute top-4 left-4 flex gap-2 z-10 pointer-events-none">
      <div
        v-if="probeStatus === 'proxied'"
        class="chip bg-black/60 text-amber-200 backdrop-blur-md border border-white/5"
      >
        via proxy
      </div>
    </div>

    <!-- Quality picker -->
    <div v-if="allQualities.length" class="absolute top-4 right-4 z-30">
      <button
        class="chip bg-black/60 text-slate-100 backdrop-blur-md border border-white/10 hover:bg-black/80 transition-colors"
        @click="showQualityMenu = !showQualityMenu"
      >
        <span class="opacity-60">Quality:</span>
        <span class="font-semibold ml-1">{{ qualityLabel }}</span>
      </button>

      <!-- Click-away backdrop -->
      <div v-if="showQualityMenu" class="fixed inset-0 -z-10" @click="showQualityMenu = false" />

      <div
        v-if="showQualityMenu"
        class="absolute right-0 mt-2 w-44 rounded-lg bg-black/90 backdrop-blur-md border border-white/10 overflow-hidden text-sm shadow-xl"
      >
        <button
          class="w-full px-3 py-2 text-left hover:bg-white/10 flex items-center justify-between"
          :class="mode === 'auto' ? 'text-accent-gold' : 'text-slate-200'"
          @click="selectAuto"
        >
          <span>Auto</span>
          <span v-if="mode === 'auto' && autoResolution" class="text-xs opacity-60">{{ autoResolution }}</span>
        </button>
        <button
          v-for="q in ladder"
          :key="q.resolution"
          class="w-full px-3 py-2 text-left hover:bg-white/10 flex items-center justify-between"
          :class="mode === 'pinned' && pinnedResolution === q.resolution ? 'text-accent-gold' : 'text-slate-200'"
          @click="selectQuality(q.resolution)"
        >
          <span>{{ q.resolution }}</span>
          <span class="text-xs opacity-50">{{ prettySize(q.size_bytes) }}</span>
        </button>
        <template v-if="riskyQualities.length">
          <div class="px-3 py-1 text-[10px] uppercase tracking-wide text-slate-500 border-t border-white/10">
            May not play
          </div>
          <button
            v-for="q in riskyQualities"
            :key="`hevc-${q.resolution}`"
            class="w-full px-3 py-2 text-left hover:bg-white/10 flex items-center justify-between"
            :class="mode === 'pinned' && pinnedResolution === q.resolution ? 'text-accent-gold' : 'text-slate-400'"
            @click="selectQuality(q.resolution)"
          >
            <span>{{ q.resolution }} <span class="opacity-50">HEVC</span></span>
            <span class="text-xs opacity-50">{{ prettySize(q.size_bytes) }}</span>
          </button>
        </template>
      </div>
    </div>

    <div
      v-if="videoError"
      class="absolute bottom-20 left-1/2 -translate-x-1/2 chip bg-red-900/90 text-red-100 border border-red-500/50 z-30"
    >
      Playback error: {{ videoError }}
    </div>

    <div
      v-if="downgradeNotice"
      class="absolute bottom-20 left-1/2 -translate-x-1/2 chip bg-black/80 text-amber-200 border border-amber-500/40 z-30"
    >
      {{ downgradeNotice }}
    </div>
  </div>
</template>

<style>
/* Make the video.js skin fill its container instead of using vjs-fluid's
   intrinsic aspect ratio (we already enforce 16:9 on the wrapper). */
.video-js {
  width: 100%;
  height: 100%;
  background: #000;
}
.video-js .vjs-tech {
  object-fit: contain;
}
/* Brand the player in our accent gold to match the rest of the UI. */
.video-js .vjs-play-progress,
.video-js .vjs-volume-level,
.video-js .vjs-slider-bar {
  background-color: #eab308;
}
.video-js .vjs-big-play-button {
  background-color: rgba(0, 0, 0, 0.6);
  border-color: rgba(255, 255, 255, 0.2);
  border-radius: 9999px;
}
</style>
