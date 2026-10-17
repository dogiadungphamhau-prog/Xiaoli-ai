// Service worker: lưu sẵn giao diện để mở nhanh. API (/chat, /models, /health) luôn đi qua mạng.
const CACHE = "xiaoli-v1";
const SHELL = ["/", "/style.css", "/app.js", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if(e.request.method !== "GET" || u.origin !== location.origin || ["/chat", "/models", "/health"].includes(u.pathname)) return;
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
