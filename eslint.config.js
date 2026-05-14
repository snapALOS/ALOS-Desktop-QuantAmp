import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores([
    'dist/**',
    'scratch/**',
    'Upgrades From Rex/**',
    'modules/*/_vendor/**',
    'modules/*/frontend/dist/**',
    'modules/*/frontend/node_modules/**',
    'backend/dist/**',
    'backend/data/**',
    'src-tauri/target/**',
    'src-tauri/resources/backend/**',
    'node_modules/**',
  ]),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    files: [
      'modules/forge/frontend/src/main.tsx',
      'src/shell/module-views.tsx',
    ],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
