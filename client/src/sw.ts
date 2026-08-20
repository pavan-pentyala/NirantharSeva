/// <reference lib="webworker" />
export {};
declare const self: ServiceWorkerGlobalScope;

/** P4.3 (plan §8.4): precache the app shell only. Do NOT cache API
 * responses — offline data lives in IndexedDB (client/src/db/schema.ts),
 * never in the HTTP cache; mixing the two produces stale reads. No fetch
 * handler below ever touches "/api/*" — only same-origin, non-API GETs are
 * served from the precache, and only as a fallback after the network.
 *
 * injectManifest mode (vite-plugin-pwa): self.__WB_MANIFEST is replaced at
 * build time with the list of built asset URLs+revisions. No Workbox
 * runtime dependency — plain Cache Storage API, since the app shell is a
 * handful of files and doesn't need Workbox's routing/strategy machinery.
 *
 * Excluded from the app's shared tsconfig (client/tsconfig.json) — the
 * webworker lib's globals (this file's `self`) and the DOM lib the rest of
 * `src/` needs cannot coexist in one TypeScript program.
 */

interface ManifestEntry {
  url: string;
  revision: string | null;
}

declare global {
  interface ServiceWorkerGlobalScope {
    __WB_MANIFEST: ManifestEntry[];
  }
}

const PRECACHE_MANIFEST = self.__WB_MANIFEST;
const CACHE_NAME = "nirantharseva-shell-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      await cache.addAll(PRECACHE_MANIFEST.map((entry) => entry.url));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never touch the API — offline data lives in IndexedDB, not the HTTP cache.
  if (url.pathname.startsWith("/api/")) return;
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      // ignoreVary: the server (vite preview's static file server, and any
      // real host serving compressed static assets) sends Vary: Accept-Encoding
      // on these responses. Cache.match() respects Vary by default, comparing
      // the *stored* request's headers against the *current* one — and the
      // install handler's cache.addAll() fetch and a real <script>/<link> tag's
      // browser-issued fetch don't send identical Accept-Encoding lists, so an
      // unqualified match() silently misses even though the entry is right
      // there. Cost of ignoring it: none here — every cached entry is this
      // app's own build output, immutable per filename hash, never re-served
      // with different content for the same URL.
      const matchOptions = { ignoreVary: true };
      const cached = await cache.match(event.request, matchOptions);
      try {
        const fresh = await fetch(event.request);
        // Best-effort refresh of the shell cache; never blocks the response.
        if (fresh.ok) void cache.put(event.request, fresh.clone());
        return fresh;
      } catch (err) {
        if (cached) return cached;
        // Navigations fall back to the cached app shell so the SPA can
        // boot and route client-side even when the exact URL was never
        // fetched before (e.g. a deep link opened while offline).
        if (event.request.mode === "navigate") {
          const shell = await cache.match("/index.html", matchOptions);
          if (shell) return shell;
        }
        throw err;
      }
    })(),
  );
});
