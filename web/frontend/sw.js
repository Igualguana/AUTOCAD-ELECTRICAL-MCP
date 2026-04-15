/**
 * sw.js — Service Worker for AutoCAD Electrical MCP PWA
 *
 * Strategy:
 *   - Static assets (HTML, CSS, JS, icons): Cache-first, update in background
 *   - API calls (/api/*):                   Network-first, offline JSON fallback
 *   - Navigation (page loads):              Cache-first, fall back to cached /
 *
 * Cache is versioned — bump CACHE_VERSION when deploying updates.
 */

'use strict';

const CACHE_VERSION = 'autocad-mcp-v2';

/** Core static assets to pre-cache on install. */
const PRECACHE_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/api.js',
  '/static/js/i18n.js',
  '/static/js/main.js',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/favicon.png',
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())   // activate immediately
  );
});

// ── Activate ─────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys =>
        Promise.all(
          keys
            .filter(k => k !== CACHE_VERSION)
            .map(k => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())  // take control of open pages
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // ── API calls: network-first ─────────────────────────────────────────────
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .catch(() =>
          new Response(
            JSON.stringify({
              error: 'Offline — backend not reachable',
              offline: true,
            }),
            {
              status: 503,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        )
    );
    return;
  }

  // ── Static assets + navigation: cache-first ──────────────────────────────
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) {
        // Return cached copy and refresh in background (stale-while-revalidate)
        const refresh = fetch(request).then(response => {
          if (response.ok && response.type === 'basic') {
            caches.open(CACHE_VERSION).then(cache => cache.put(request, response.clone()));
          }
          return response;
        }).catch(() => {/* ignore — we already have a cached response */});
        return cached;
      }

      // Not in cache — fetch from network
      return fetch(request)
        .then(response => {
          if (response.ok && response.type === 'basic') {
            caches.open(CACHE_VERSION)
              .then(cache => cache.put(request, response.clone()));
          }
          return response;
        })
        .catch(() => {
          // Offline fallback for navigation requests
          if (request.mode === 'navigate') {
            return caches.match('/');
          }
          // For other requests just let the browser show its error
        });
    })
  );
});
