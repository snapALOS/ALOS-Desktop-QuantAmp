/**
 * ALOSForge — Module entry point
 *
 * In ALOS v0.2, Forge is shell-mounted (not standalone). This file exists
 * for module isolation and re-exports the App component and key services
 * so other parts of the system can import from this barrel.
 *
 * The standalone ReactDOM.createRoot bootstrap has been removed.
 * Forge is now mounted by ForgeView.tsx in the shell.
 */

export { default as ForgeApp } from './App';
export { useIDEStore } from './store/useIDEStore';
export { TauriAdapter } from './services/adapters/TauriAdapter';
export type { EnvironmentAdapter } from './services/adapters/EnvironmentAdapter';
