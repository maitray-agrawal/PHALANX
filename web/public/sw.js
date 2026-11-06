/**
 * PHALANX Service Worker
 *
 * Caches strictly hashed immutable static assets (/assets/*).
 * Never caches HTML documents, shell navigation, or API responses.
 */

const CACHE_NAME = "phalanx-static-v1";

self.addEventListener("install", () => {
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

  // Never intercept or cache API requests, HTML navigation documents, mutations, or non-GET requests
  if (
    url.pathname.startsWith("/v1/") ||
    url.pathname.startsWith("/api/") ||
    url.pathname === "/" ||
    url.pathname.endsWith(".html") ||
    event.request.mode === "navigate" ||
    event.request.method !== "GET" ||
    event.request.headers.has("Authorization")
  ) {
    return;
  }

  // Cache only immutable hashed static assets under /assets/
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
  }
});

