import WorkflowApp from '../../../modules/current/frontend/src/App'
import '../../../modules/current/frontend/src/index.css'

/**
 * CurrentView Adapter (Workflow)
 * 
 * Wraps the vendored Workflow (ALOSCurrent) application.
 * Note: Uses MUICssBaseline indirectly via the vendored app's styles.
 */
export function CurrentView() {
  return (
    <div className="h-full w-full overflow-hidden alos-current-wrapper">
      <WorkflowApp />
      <style>{`
        .alos-current-wrapper > div { height: 100% !important; }
        /* Hide the legacy sidebar if it clutters the ALOS shell */
        .alos-current-wrapper .sidebar { width: 200px !important; } 
      `}</style>
    </div>
  )
}

// AtlasView lives in src/components/atlas/AtlasView.tsx as of 0152 —
// it's a real visual dependency map, not a placeholder. Imported
// directly by the module-view dispatcher.

/**
 * ChamberView Adapter (Sandbox)
 * 
 * ALOSChamber diagnostic dashboard.
 */
import { ChamberView } from '../../../modules/chamber/frontend/src/ChamberView'
export { ChamberView }
