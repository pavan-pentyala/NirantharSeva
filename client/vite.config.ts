import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const apiProxy = {
  "/api": {
    target: "http://api:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [
    react(),
    // P4.3 (plan §8.4): injectManifest mode, own service worker
    // (src/sw.ts) — precaches the app shell only, never API responses.
    // No devOptions: vite-plugin-pwa's dev-mode SW injects an empty
    // precache manifest, which cannot actually serve the shell offline —
    // real offline-reload behavior only exists in a built+previewed app.
    // See client/tests/pwa-offline-reload.spec.ts for how that's tested.
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectRegister: "auto",
      manifest: {
        name: "NirantharSeva",
        short_name: "NirantharSeva",
        description: "Offline-first referral tracking",
        theme_color: "#32679b",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/login",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: apiProxy,
  },
  // vite preview serves the real production build (dist/) with its real
  // service worker precache — used only by pwa-offline-reload.spec.ts,
  // which needs genuine offline shell-loading, not dev mode.
  preview: {
    host: "0.0.0.0",
    port: 4173,
    proxy: apiProxy,
  },
});
