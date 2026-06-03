export default defineNuxtPlugin((nuxtApp) => {
  const handleChunkError = () => {
    if (sessionStorage.getItem('chunk-reload-attempted')) return
    sessionStorage.setItem('chunk-reload-attempted', '1')
    window.location.reload()
  }

  nuxtApp.hook('app:chunkError', handleChunkError)
  window.addEventListener('vite:preloadError', handleChunkError)

  nuxtApp.hook('app:mounted', () => {
    sessionStorage.removeItem('chunk-reload-attempted')
  })
})
