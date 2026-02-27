import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import path from "path"

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [react()],
  root: "src-ui",
  clearScreen: false,
  css: {
    postcss: path.resolve(__dirname),
  },
  server: {
    port: 1420,
    strictPort: false,
    host: host || false,
    hmr: host
      ? { protocol: "ws", host, port: 1421 }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
})

