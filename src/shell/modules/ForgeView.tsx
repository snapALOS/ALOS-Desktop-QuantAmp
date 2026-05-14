import { useEffect } from 'react'
import ForgeApp from '../../../modules/forge/frontend/src/App'
import { useIDEStore } from '../../../modules/forge/frontend/src/store/useIDEStore'
import { TauriAdapter } from '../../../modules/forge/frontend/src/services/adapters/TauriAdapter'

/**
 * ForgeView — ALOS shell adapter for the Forge IDE module.
 *
 * Initializes the ALOS-aware TauriAdapter and mounts the Forge App
 * component. The Forge App has been rewritten to omit standalone
 * title/status bars, so no CSS overrides are needed.
 */
export function ForgeView() {
  const { setAdapter, setPlatform } = useIDEStore()

  useEffect(() => {
    const adapter = new TauriAdapter()
    setAdapter(adapter)

    // Boot: detect platform for OS-specific behavior
    void adapter.getPlatform().then(setPlatform)

    console.log('[ForgeView] ALOS bridge initialized.')
  }, [setAdapter, setPlatform])

  return (
    <div className="h-full w-full overflow-hidden">
      <ForgeApp />
    </div>
  )
}
