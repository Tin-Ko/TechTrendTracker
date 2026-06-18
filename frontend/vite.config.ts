import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev: Vite serves the SPA on :5173 and proxies API calls to the Go
// backend on :8080. In prod the Go binary serves the built static files
// out of frontend/dist/ alongside the API, so no proxy is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/skills": "http://localhost:8080",
      // Add more API paths here as the backend grows.
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
