/**
 * Module view dispatcher — single extension point for the ModuleShell.
 *
 * The shell is deliberately oblivious to which modules exist. It calls
 * `defaultRenderFor(activeId)` and this file decides what to mount.
 *
 * To add a new module view:
 *   1. Import the view component.
 *   2. Add a `case '<module_id>':` branch.
 *
 * Unknown module ids fall through to a generic placeholder.
 */

import type { ReactElement } from 'react'
import { ChatView } from '@/components/chat/ChatView'
import { AtlasView } from '@/components/atlas/AtlasView'
import { ScoutView } from '@/components/scout/ScoutView'
import { ForgeView } from '@/shell/modules/ForgeView'
import { CurrentView, ChamberView } from '@/shell/modules/ModuleViews'
import { SettingsView } from '@/shell/modules/SettingsView'

function ModulePlaceholder({ moduleId }: { moduleId: string }): ReactElement {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center text-muted-foreground">
        <p className="text-lg font-medium capitalize">{moduleId}</p>
        <p className="mt-1 text-sm">This module is not yet available in v0.2.</p>
      </div>
    </div>
  )
}

export function defaultRenderFor(moduleId: string): ReactElement {
  switch (moduleId) {
    case 'chat':
      return <ChatView />
    case 'forge':
      return <ForgeView />
    case 'current':
      return <CurrentView />
    case 'atlas':
      return <AtlasView />
    case 'chamber':
      return <ChamberView />
    case 'scout':
      return <ScoutView />
    case 'settings':
      return <SettingsView />
    default:
      return <ModulePlaceholder moduleId={moduleId} />
  }
}
