/*
 * The Green Buffet service worker: lets the screens open with no network.
 *
 * What it keeps, and how:
 * - The page itself (index.html): fetched fresh every time the network is
 *   up, so an update shows at once; the kept copy is used only when the
 *   server cannot be reached.
 * - The built scripts, styles, fonts and pictures under /assets/: their names
 *   change with every build, so a kept copy is always the right one and is
 *   served straight from the device.
 * - The icons and the manifest.
 *
 * What it never touches: anything under /api/. Sales, prices, sign-in and
 * everything else with data always go to the server; the till keeps its own
 * offline sales separately and sends them itself. Nothing personal or secret
 * is ever put in this cache.
 */
const VERSION = 'gb-1.27.0'
const SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png']
// Filled in by the build (vite.config.ts) with every built file.
const BUILT = []

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION)
      // The page and icons must be kept; the built files are best effort, one
      // at a time, so one missing file cannot stop the rest.
      .then((cache) => cache.addAll(SHELL).then(() => Promise.all(BUILT.map((f) => cache.add(f).catch(() => undefined))))).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  // Older versions' copies are removed once this one takes over.
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return

  // A page: the network first, the kept page if the network fails.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(VERSION).then((cache) => cache.put('/', copy))
          }
          return response
        })
        .catch(() => caches.match('/', { ignoreVary: true }).then((kept) => kept || Response.error())),
    )
    return
  }

  // Built files: from the device when kept, otherwise fetched and kept.
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || url.pathname === '/manifest.webmanifest') {
    event.respondWith(
      // ignoreVary: the server marks files "Vary: Origin", and the page asks
      // with an Origin header the worker's own copies were fetched without.
      // The file is the same either way.
      caches.match(request, { ignoreVary: true }).then((kept) => {
        if (kept) return kept
        return fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(VERSION).then((cache) => cache.put(request, copy))
          }
          return response
        })
      }),
    )
  }
})
