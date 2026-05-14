/**
 * Active module store — persists the last-active module across sessions.
 *
 * RFC-0001 Decision 7: stored in localStorage via Zustand persist.
 * On load, the shell validates the persisted id against the live registry
 * and falls back to 'chat' if it's unavailable or hidden.
 *
 * The v2 storage key intentionally clears pre-release persisted module state.
 * Early Forge builds could leave users reopening directly into a broken IDE
 * view, so v0.2 starts from Chat once after upgrade and persists normally
 * from there.
 */

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface ActiveModuleStore {
  activeId: string
  setActive: (id: string) => void
}

export const useActiveModule = create<ActiveModuleStore>()(
  persist(
    (set) => ({
      activeId: 'chat',
      setActive: (id) => set({ activeId: id }),
    }),
    {
      name: 'alos:active-module:v2',
      storage: createJSONStorage(() => localStorage),
    },
  ),
)
