/* Productivity Buddy service worker.
 * Network-first: when the server is reachable you always get fresh data.
 * When it isn't, the last good copy of the dashboard opens instead, so tasks
 * can still be added to the offline queue and synced later.
 */
const CACHE = 'pb-shell-v1';
const SHELL = ['/', '/static/style.css', '/static/app.js'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function cacheable(request, response) {
  if (!response || !response.ok || response.type !== 'basic') return false;
  // Pages that carry one-time messages ("Task added") must not be replayed offline.
  return response.headers.get('X-PB-Offline-Cache') !== 'no';
}

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only same-origin GETs for the dashboard and static files. API calls always go
  // to the network so the app can tell when the server is really unreachable.
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  const isPage = request.mode === 'navigate' && url.pathname === '/';
  const isStatic = url.pathname.startsWith('/static/');
  if (!isPage && !isStatic) return;

  // Store the dashboard under '/' regardless of ?focus=… so any visit refreshes it.
  const key = isPage ? '/' : request;

  event.respondWith(
    fetch(request)
      .then(response => {
        if (cacheable(request, response)) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(key, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(key).then(cached => cached || Response.error()))
  );
});
