import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

// O build vai direto para server/app/static, que o FastAPI serve: assim o
// deploy (Render) não precisa de Node. Em desenvolvimento (`npm run dev`),
// as chamadas /api e /ws vão para o servidor Python em 127.0.0.1:8000.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
})
