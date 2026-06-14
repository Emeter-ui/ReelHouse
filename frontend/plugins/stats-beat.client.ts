// Per-tab visitor heartbeat. A persistent localStorage UUID identifies the
// session; the first beat with a new UUID increments the cumulative counter,
// subsequent beats just mark the session active. Skips when the tab is hidden
// so we don't inflate "active now" with backgrounded tabs.

const SID_KEY = 'rh_sid'
const BEAT_INTERVAL_MS = 30_000

function getSid(): string {
  let sid = localStorage.getItem(SID_KEY)
  if (!sid) {
    sid = crypto.randomUUID()
    localStorage.setItem(SID_KEY, sid)
  }
  return sid
}

export default defineNuxtPlugin(() => {
  const { public: { apiBase } } = useRuntimeConfig()
  const sid = getSid()

  const beat = () => {
    if (document.visibilityState !== 'visible') return
    fetch(`${apiBase}/api/stats/beat?sid=${encodeURIComponent(sid)}`, {
      method: 'GET',
      keepalive: true,
    }).catch(() => {})
  }

  beat()
  setInterval(beat, BEAT_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') beat()
  })
})
