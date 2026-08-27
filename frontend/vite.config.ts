import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// PWA per PRD §7: installable via "Add to Home Screen", offline via a
// service worker + IndexedDB. Deliberately NOT relying on the Web
// Background Sync API (Safari/WebKit never implemented it) — sync is
// driven from app code (online event + foreground timer, see
// src/sync/syncManager.ts), so the service worker's only job here is
// precaching the app shell so the scan screen loads with zero signal.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "Race Timing — Checkpoint Scanner",
        short_name: "Race Timing",
        description: "Volunteer checkpoint scanning for race timing, offline-first.",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon-192.svg", sizes: "192x192", type: "image/svg+xml", purpose: "any maskable" },
          { src: "icon-512.svg", sizes: "512x512", type: "image/svg+xml", purpose: "any maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallback: "/index.html",
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
  },
});
