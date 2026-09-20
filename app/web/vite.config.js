import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  root: ".",
  base: "/",
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/models": "http://127.0.0.1:3796",
      "/vendor": "http://127.0.0.1:3796",
      "/codexpet": "http://127.0.0.1:3796",
      "/media": "http://127.0.0.1:3796",
      "/api": "http://127.0.0.1:3796",
      "/ws": {
        target: "ws://127.0.0.1:3796",
        ws: true,
      },
    },
  },
});
