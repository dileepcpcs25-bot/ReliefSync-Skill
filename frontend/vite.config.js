import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.RELIEFSYNC_FRONTEND_PORT || 5191), strictPort: true,
    proxy: { '/api': { target: `http://127.0.0.1:${process.env.RELIEFSYNC_API_PORT || 8015}`, changeOrigin: true }, '/health': { target: `http://127.0.0.1:${process.env.RELIEFSYNC_API_PORT || 8015}`, changeOrigin: true } },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.js'], css: false, restoreMocks: true },
})
