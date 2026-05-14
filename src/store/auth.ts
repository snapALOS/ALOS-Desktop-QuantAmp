import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { User } from '@/types/api'

/**
 * Auth store.
 *
 * For v1 the API key is persisted to localStorage (inside Tauri's webview,
 * which is isolated per-app — not shared with the user's browser).
 * A later pass will migrate this to the OS keychain via a Tauri plugin.
 */

interface AuthState {
  apiKey: string | null
  user: User | null
  setApiKey: (key: string | null) => void
  setUser: (user: User | null) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      apiKey: null,
      user: null,
      setApiKey: (apiKey) => set({ apiKey }),
      setUser: (user) => set({ user }),
      logout: () => set({ apiKey: null, user: null }),
    }),
    {
      name: 'alos-auth',
      storage: createJSONStorage(() => localStorage),
      // Never persist the user object — always re-fetch on launch
      partialize: (state) => ({ apiKey: state.apiKey }),
    }
  )
)
