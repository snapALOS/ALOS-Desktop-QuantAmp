/**
 * Forge module — Tauri command contract (stub).
 *
 * v0.2 Forge operates entirely on top of the core filesystem + terminal
 * commands exposed in `src/contracts/tauri-commands.ts` — it does not yet
 * register module-prefixed `forge_*` commands. This file exists so
 * MODULE.toml's contracts.commands path resolves and future Forge-specific
 * IPC lands here rather than in the module's private surface.
 *
 * When adding a Forge command:
 *   1. Register `forge_<verb>_<object>` in `src-tauri/src/lib.rs` under the
 *      `// Forge` group (see modules_ipc.rs for the convention).
 *   2. Implement it in `src-tauri/src/forge/commands.rs` (create that file).
 *   3. Export a typed wrapper below via `createModuleInvoke('forge')` from
 *      `@/shell/module-ipc`.
 */

export {}
