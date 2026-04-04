import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    conditions: ["browser"],
  },
  build: {
    outDir: "../src/compendium/web/static",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:17394",
      "/ws": { target: "ws://127.0.0.1:17394", ws: true },
    },
  },
});
