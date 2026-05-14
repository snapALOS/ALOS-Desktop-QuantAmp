/**
 * ActivityBar — narrow (48 px) vertical bar on the far left, VS Code style.
 *
 * RFC-0001: Rust is the source of truth, but the frontend renders icons
 * from the registry loaded at shell mount. Keyboard shortcuts Cmd/Ctrl+1..9
 * activate the Nth *visible* entry.
 */

import { useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { resolveIcon } from '@/shell/icon-map'
import { useActiveModule } from '@/store/active-module'
import type { ModuleEntry } from '@/shell/module-registry'
import { visibleEntries } from '@/shell/module-registry'
import logo from '@/assets/logo-alos.svg'

interface ActivityBarProps {
  registry: ModuleEntry[]
}

export function ActivityBar({ registry }: ActivityBarProps) {
  const activeId = useActiveModule((s) => s.activeId)
  const setActive = useActiveModule((s) => s.setActive)

  const visible = visibleEntries(registry)

  const activateModule = useCallback(
    (m: ModuleEntry) => {
      if (!m.available) return
      setActive(m.id)
    },
    [setActive],
  )

  // Keyboard: Cmd/Ctrl + 1..9 activates Nth visible entry (RFC-0001 Decision 9)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey
      if (!mod) return

      const digit = parseInt(e.key, 10)
      if (isNaN(digit) || digit < 1 || digit > 9) return

      const idx = digit - 1
      if (idx >= visible.length) return

      const target = visible[idx]
      if (!target || !target.available) return

      e.preventDefault()
      setActive(target.id)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [visible, setActive])

  return (
    <aside className="flex h-screen w-12 flex-col items-center border-r border-border bg-card/40 py-3">
      {/* Logo at top */}
      <div className="flex h-8 w-8 items-center justify-center mb-3">
        <img src={logo} alt="ALOS" className="h-6 w-6" />
      </div>

      {/* Module icons */}
      <nav className="flex flex-1 flex-col items-center gap-1">
        {visible.map((m) => {
          const Icon = resolveIcon(m.icon)
          const isActive = m.id === activeId

          return (
            <button
              key={m.id}
              onClick={() => activateModule(m)}
              title={
                m.available
                  ? m.displayName
                  : `${m.displayName} — unavailable. Click for details.`
              }
              aria-label={m.displayName}
              className={cn(
                'relative flex h-10 w-10 items-center justify-center rounded-lg transition',
                // Active: left-edge accent (RFC-0001 spec)
                isActive && 'border-l-2 border-primary bg-primary/15 text-primary',
                // Inactive
                !isActive && m.available && 'text-muted-foreground hover:bg-muted hover:text-foreground',
                // Unavailable: 50% opacity, not-allowed
                !m.available && 'opacity-50 cursor-not-allowed text-muted-foreground',
              )}
            >
              <Icon size={18} />
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
