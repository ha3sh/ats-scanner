import { defineConfig } from "vite";

// Built output is committed: see docs/ARCHITECTURE.md, "One-command run and build".
export default defineConfig({
  build: {
    outDir: "../src/ats_scanner/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
