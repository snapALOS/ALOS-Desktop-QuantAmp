import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@forge': path.resolve(__dirname, './modules/forge/frontend/src'),
      '@current': path.resolve(__dirname, './modules/current/frontend/src'),
      '@atlas': path.resolve(__dirname, './modules/atlas/frontend/src'),
    },
  },
  test: {
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      'scratch/**',
      'Upgrades From Rex/**',
      'modules/*/_vendor/**',
      'modules/*/frontend/dist/**',
      'modules/*/frontend/node_modules/**',
      'backend/dist/**',
      'backend/data/**',
      'src-tauri/target/**',
      'src-tauri/resources/backend/**',
    ],
  },
})
