//! ALOS Module IPC Conventions
//!
//! Modules follow a strict naming convention for Tauri commands so that:
//!   * names never collide across modules,
//!   * `grep <module_id>_` is sufficient to audit a module's IPC surface,
//!   * the Rust registration list in `lib.rs` and the TypeScript contract in
//!     `src/contracts/tauri-commands.ts` can be diffed line-for-line.
//!
//! # Naming Rule
//!
//! `<module_id>_<verb>_<object>` — all snake_case, no abbreviations.
//!
//! Examples:
//!   * `forge_open_file`
//!   * `atlas_impact_symbol`
//!   * `current_trigger_workflow`
//!
//! Core (shell-level) commands use the `core_` prefix and do NOT carry a
//! module id — they are not owned by any module:
//!   * `core_fs_read_file`
//!   * `core_terminal_create`
//!
//! # Rust side
//!
//! Module commands live in `src-tauri/src/<module_id>/commands.rs` and are
//! registered in `src-tauri/src/lib.rs` inside a labeled comment block:
//!
//! ```ignore
//! .invoke_handler(tauri::generate_handler![
//!     // Forge
//!     forge::commands::forge_open_file,
//!     forge::commands::forge_close_file,
//!     // Atlas
//!     atlas::commands::atlas_impact_symbol,
//! ])
//! ```
//!
//! The comment block is load-bearing: `#[rustfmt::skip]` on `pub fn run()`
//! preserves the grouping. Removing it collapses the list and makes the
//! subsystem boundaries invisible.
//!
//! # Frontend side: `createModuleInvoke`
//!
//! Modules MUST NOT import `@tauri-apps/api/core` directly — all IPC goes
//! through `@/api/tauri` so browser-preview mode degrades gracefully. The
//! preferred pattern in module code is the `createModuleInvoke` helper, which
//! prefixes every call with the module id and centralises error handling:
//!
//! ```ts
//! // src/shell/modules/forge/ipc.ts
//! import { createModuleInvoke } from '@/shell/module-ipc'
//!
//! const forgeInvoke = createModuleInvoke('forge')
//!
//! export const forgeOpenFile = (path: string) =>
//!   forgeInvoke<FileOpenResult>('open_file', { path })     // -> forge_open_file
//!
//! export const forgeCloseFile = (id: string) =>
//!   forgeInvoke<void>('close_file', { id })                // -> forge_close_file
//! ```
//!
//! `createModuleInvoke('forge')('open_file', args)` dispatches to the Tauri
//! command `forge_open_file`. The factory is the single chokepoint that
//! enforces the naming rule in TypeScript — callers cannot accidentally hit
//! another module's namespace, and `grep "createModuleInvoke('forge')"`
//! lists every forge consumer.
//!
//! # Adding a new module command
//!
//! 1. Add the `#[tauri::command]` in `src-tauri/src/<module_id>/commands.rs`
//!    using the `<module_id>_<verb>_<object>` name.
//! 2. Register it in the matching comment block in `lib.rs`.
//! 3. Expose it in the module's `src/shell/modules/<module_id>/ipc.ts` via
//!    `createModuleInvoke('<module_id>')`.
//! 4. Add a type test in `src/contracts/tauri-commands.ts` OR the module's
//!    own `contracts/commands.ts` if the command is module-local.
//!
//! See `docs/CONVENTIONS.md` for the full specification.
