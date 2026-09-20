import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from 'node:fs';

let port = 3796;
try { port = JSON.parse(readFileSync(new URL('../../data/runtime_config.json', import.meta.url), 'utf8')).web_port || port; } catch {}
port = Number(process.env.XINBOT_WEB_PORT || port);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Invalid backend port');
const backend = `http://127.0.0.1:${port}`;

export default defineConfig({
  plugins: [vue()],
  root: ".",
  base: "/",
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      "/models": backend,
      "/vendor": backend,
      "/codexpet": backend,
      "/media": backend,
      "/api": backend,
      "/ws": {
        target: `ws://127.0.0.1:${port}`,
        ws: true,
      },
    },
  },
});
