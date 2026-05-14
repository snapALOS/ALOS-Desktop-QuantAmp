/**
 * Module registry — typed list of modules loaded from Rust at startup.
 *
 * RFC-0001 Decision 1: Rust is the single source of truth. The frontend calls
 * `list_modules` via Tauri IPC and never touches the filesystem.
 */

import { invoke, isTauri } from '@/api/tauri'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ModuleEntry {
  id: string
  displayName: string
  version: string
  order: number
  icon: string           // kebab-case lucide icon name
  route: string          // e.g. '/forge', '/chat'
  available: boolean     // false → grayed out, click for error details
  errorMessage: string | null
  hidden: boolean        // if true, in registry but not in activity bar
  kind: 'module' | 'builtin'
}

// ---------------------------------------------------------------------------
// Rust ↔ TS field-name bridge
// ---------------------------------------------------------------------------

/** Raw shape from Rust (snake_case). */
interface RustModuleEntry {
  id: string
  display_name: string
  version: string
  order: number
  icon: string
  route: string
  available: boolean
  error_message: string | null
  hidden: boolean
  kind: string
}

function fromRust(raw: RustModuleEntry): ModuleEntry {
  return {
    id: raw.id,
    displayName: raw.display_name,
    version: raw.version,
    order: raw.order,
    icon: raw.icon,
    route: raw.route,
    available: raw.available,
    errorMessage: raw.error_message,
    hidden: raw.hidden,
    kind: raw.kind as 'module' | 'builtin',
  }
}

// ---------------------------------------------------------------------------
// Fallback built-ins (used when Tauri IPC is unavailable, e.g. browser preview)
// ---------------------------------------------------------------------------

function fallbackBuiltins(): ModuleEntry[] {
  return [
    {
      id: 'forge',
      displayName: 'Forge',
      version: '0.2.0',
      order: 10,
      icon: 'code',
      route: '/forge',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'module',
    },
    {
      id: 'current',
      displayName: 'Current',
      version: '0.2.0',
      order: 20,
      icon: 'workflow',
      route: '/current',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'module',
    },
    {
      id: 'atlas',
      displayName: 'Atlas',
      version: '0.2.0',
      order: 30,
      icon: 'database',
      route: '/atlas',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'module',
    },
    {
      id: 'chamber',
      displayName: 'Chamber',
      version: '0.2.0',
      order: 40,
      icon: 'shield',
      route: '/chamber',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'module',
    },
    {
      id: 'chat',
      displayName: 'Chat',
      version: '0.1.0',
      order: 90,
      icon: 'message-square',
      route: '/chat',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'builtin',
    },
    {
      id: 'extensions',
      displayName: 'Extensions',
      version: '0.1.0',
      order: 95,
      icon: 'puzzle',
      route: '/extensions',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'builtin',
    },
    {
      id: 'scout',
      displayName: 'Scout',
      version: '0.1.0',
      order: 97,
      icon: 'activity',
      route: '/scout',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'builtin',
    },
    {
      id: 'settings',
      displayName: 'Settings',
      version: '0.1.0',
      order: 99,
      icon: 'settings',
      route: '/settings',
      available: true,
      errorMessage: null,
      hidden: false,
      kind: 'builtin',
    },
  ]
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Load the full module registry.
 *
 * In a Tauri context this calls `list_modules` (Rust) which returns built-ins
 * merged with scanned MODULE.toml entries, sorted by `order`. Outside Tauri
 * (e.g. browser preview) it falls back to hardcoded built-ins.
 */
export async function loadRegistry(): Promise<ModuleEntry[]> {
  if (!isTauri()) {
    return fallbackBuiltins()
  }

  try {
    const raw = await invoke<RustModuleEntry[]>('list_modules')
    return raw.map(fromRust)
  } catch (err) {
    console.error('[module-registry] Failed to load from Rust, using fallbacks:', err)
    return fallbackBuiltins()
  }
}

/**
 * Filter the registry to entries that should appear in the activity bar:
 * visible (not hidden) entries, sorted by order.
 */
export function visibleEntries(registry: ModuleEntry[]): ModuleEntry[] {
  return registry.filter((m) => !m.hidden)
}
