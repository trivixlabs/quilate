/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      // changeOrigin: o Host chega como 127.0.0.1:8000, que o LocalOnly do backend aceita
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: "../backend/quilate/api/static", emptyOutDir: true,
    // gráfico e animação em blocos próprios: o bloco principal fica abaixo do aviso de 500 kB
    rolldownOptions: { output: { codeSplitting: { groups: [
      { name: "charts", test: /node_modules\/lightweight-charts/ }, { name: "motion", test: /node_modules\/motion/ },
    ] } } },
  },
  test: { environment: "jsdom", globals: false, setupFiles: ["src/test/setup.ts"] },
});
