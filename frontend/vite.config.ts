import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development the API runs on :8000 and Vite proxies /api and /media to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 8473,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/media': 'http://127.0.0.1:8000',
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
})
