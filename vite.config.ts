import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// Tauri expects a fixed port, fail if that port is not available
const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@forge': path.resolve(__dirname, './modules/forge/frontend/src'),
      '@current': path.resolve(__dirname, './modules/current/frontend/src'),
      '@atlas': path.resolve(__dirname, './modules/atlas/frontend/src'),
    },
    dedupe: [
      '@emotion/react',
      '@emotion/styled',
      '@mui/icons-material',
      '@mui/material',
      '@mui/system',
    ],
  },
  // Vite options tailored for Tauri
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 5174,
        }
      : undefined,
    watch: {
      // Tell vite to ignore watching `src-tauri`
      ignored: ['**/src-tauri/**'],
    },
  },
})
