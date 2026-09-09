import { defineConfig } from "vite";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8010",
        changeOrigin: false,
        timeout: 180000,
      },
    },
  },
  test: { environment: "jsdom" },
  build: {
    rollupOptions: { output: { manualChunks: { charts: ["recharts"] } } },
  },
});
