/**
 * PHALANX Service Worker
 *
 * Invariant (manual rule):
 * - NO service worker caching for API endpoints (/v1/*) or authenticated responses.
 * - Caches ONLY hashed static assets and application shell.
 * - Always passes financial API requests directly to the network without interception.
 */

const CACHE_NAME = "phalanx-static-v1";
const STATIC_ASSETS = [
  "/",
  "/manifest.json",
  "/favicon.svg",
  "/favicon.ico",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // 1. Never intercept or cache API requests, mutations, or non-GET requests
  if (
    url.pathname.startsWith("/v1/") ||
    url.pathname.startsWith("/api/") ||
    event.request.method !== "GET" ||
    event.request.headers.has("Authorization")
  ) {
    return; // Pass through to network
  }

  // 2. Cache-first strategy for hashed immutable static assets
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // 3. Network-first strategy for shell navigation documents
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/"))
    );
  }
});

