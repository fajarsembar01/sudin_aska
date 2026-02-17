const SW_VERSION = "aska-dt-v1";
const SHELL_CACHE = `${SW_VERSION}-shell`;
const RUNTIME_CACHE = `${SW_VERSION}-runtime`;

const SHELL_URLS = [
  "/daftar-tamu/saya/riwayat?tab=beranda",
  "/static/css/dashboard.css",
  "/static/logo/logo.png",
  "/static/pwa/aska-dt-manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)).catch(() => Promise.resolve())
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("aska-dt-") && key !== SHELL_CACHE && key !== RUNTIME_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    networkPromise.catch(() => null);
    return cached;
  }
  const network = await networkPromise;
  return network || new Response("Offline", { status: 503 });
}

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    return caches.match("/daftar-tamu/saya/riwayat?tab=beranda");
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  const isFeed = url.pathname.startsWith("/daftar-tamu/saya/riwayat/feed");
  const isThumb = url.pathname.startsWith("/daftar-tamu/media/photo-thumb/");
  const isHistoryNav = request.mode === "navigate" && url.pathname.startsWith("/daftar-tamu/saya/riwayat");

  if (isFeed || isThumb) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }
  if (isHistoryNav) {
    event.respondWith(networkFirst(request));
  }
});
