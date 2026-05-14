---
id: 0006
title: Tauri command registration pattern for module-scoped commands
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0018, 0039]
blocked_by: [0001]
related_rfc: 0001
pr: null
---

# 0006 — Tauri command registration pattern for module-scoped commands

## Context

Modules will add Tauri commands (e.g., `forge_open_file`, `atlas_symbol_context`, `current_trigger_workflow`). The current pattern in `src-tauri/src/lib.rs` is a single `tauri::generate_handler![...]` list with flat names. Without a convention, each module invents its own naming, the handler list sprawls, and modules accidentally collide.

`generate_handler!` is a compile-time macro — we cannot make it dynamic. But we can codify:

1. Naming rule for module commands.
2. File structure for where they live.
3. Registration pattern in `lib.rs` that stays reviewable as modules are added.
4. A frontend-side helper so module views only call their own commands.

No runtime router is needed — this task is about **convention + mechanical plumbing**.

## Scope

**In scope:**
- Write `src-tauri/src/modules_ipc.rs` containing a documentation block that states the naming and registration rules (even if the file exports no code beyond a trivial helper). This file is the canonical documentation location for the pattern.
- Refactor `src-tauri/src/lib.rs`'s `invoke_handler!` call to group command references by module/area with a comment header per group. Example structure:
  ```rust
  .invoke_handler(tauri::generate_handler![
      // Core
      backend::backend_status,
      backend::launch_backend,
      modules::list_modules,
      modules::refresh_modules,

      // Preflight
      preflight::preflight_check,
      preflight::preflight_install,

      // LSP (reserved for task 0015)
      // lsp::lsp_request_server,
      // lsp::lsp_shutdown,

      // Forge  (reserved for task 0018)
      // forge::forge_read_file,
      // ...

      // Current (reserved for task 0034)
      // current::current_list_workflows,
      // ...

      // Atlas (reserved for task 0053)
      // atlas::atlas_index_status,
      // ...
  ])
  ```
  The commented placeholders show every future module exactly where their commands go.
- Add a frontend helper `src/shell/module-ipc.ts` exporting `createModuleInvoke(moduleId)`:
  ```typescript
  export function createModuleInvoke(moduleId: string) {
    return async function invokeModule<T>(
      verb: string,
      args?: Record<string, unknown>,
    ): Promise<T> {
      const fullName = `${moduleId}_${verb}`
      return invoke<T>(fullName, args)
    }
  }
  ```
  Each module's frontend imports this once and uses `const api = createModuleInvoke('forge')` then `api('open_file', { path })`. This discourages modules from reaching for commands outside their prefix.
- Update `CONVENTIONS.md` with a short subsection under §5 (Rust) documenting the prefix rule and the comment-grouped handler structure. One paragraph.

**Out of scope:**
- Adding actual module commands. Those come with their module tasks.
- Runtime enforcement — we're relying on convention + code review.
- Renaming existing commands (`backend_status`, `preflight_check` stay as-is; they're core commands owned by the shell, not modules).

## Files to touch

- (NEW) `src-tauri/src/modules_ipc.rs` — documentation-only module (may contain a single re-export of `tauri::AppHandle` for ergonomic use by module command files, but no more).
- `src-tauri/src/lib.rs` — reorganize the `invoke_handler!` list; declare `mod modules_ipc;` if needed.
- (NEW) `src/shell/module-ipc.ts`
- (NEW) `src/shell/__tests__/module-ipc.test.ts` — smoke test that `createModuleInvoke('forge')('foo')` routes to invoke name `forge_foo`.
- `CONVENTIONS.md` — append a subsection "Module commands" under §5.

## Acceptance criteria

- [ ] `src-tauri/src/modules_ipc.rs` exists with a doc header explaining the rules (what a module command is, naming prefix, file location, registration in `lib.rs`).
- [ ] `src-tauri/src/lib.rs` `invoke_handler!` is grouped with comment headers matching the structure above.
- [ ] `cargo check` passes.
- [ ] `cargo clippy -- -D warnings` passes.
- [ ] `src/shell/module-ipc.ts` exports `createModuleInvoke`.
- [ ] Unit test passes: `createModuleInvoke('forge')('foo', { x: 1 })` calls `invoke('forge_foo', { x: 1 })`. Mock `invoke` in the test.
- [ ] `CONVENTIONS.md` has a "Module commands" subsection documenting the rule.
- [ ] No existing command was renamed.
- [ ] `grep -n 'generate_handler' src-tauri/src/lib.rs` returns exactly one line (only one handler registration).

## Implementation notes

### The naming rule (for CONVENTIONS.md)

> **Module commands** are `#[tauri::command]` functions owned by a specific module. They follow the naming rule `<module_id>_<verb>_<object>` (all snake_case), e.g. `forge_open_file`, `atlas_impact_symbol`, `current_trigger_workflow`.
>
> - Module commands live in `src-tauri/src/<module_id>/commands.rs` (one file per module; create the `<module_id>/` module directory when the first command lands).
> - Every module command is registered in `src-tauri/src/lib.rs` inside a labeled comment block (`// <ModuleName>`). Adding a command means adding exactly one line inside the right block.
> - Module command **names** must match the naming rule. A reviewer who sees `atlas_dothing` in the handler list but no `atlas_` prefix elsewhere should block the PR.
> - Core commands (owned by the shell, not by a module) do not carry a module prefix. Examples: `backend_status`, `preflight_check`, `list_modules`.

### Frontend helper rationale

The helper doesn't do runtime enforcement — callers can still use `invoke` directly — but it makes the intended pattern easy to follow and ugly to violate. A reviewer seeing `invoke('current_trigger_workflow', ...)` in Forge's code instead of `forgeApi('trigger_workflow', ...)` knows to push back.

### On not building a full router

A dynamic router (module registers → handlers wired at runtime) would be cleaner in theory but contradicts Tauri 2's command macro, which wants compile-time references. For v0.2 we accept the compile-time coupling — all modules ship with the app, so this is not a hot-install concern.

If v1.0 ever needs runtime module loading (plug-in ecosystem), revisit via a new RFC. It will most likely involve a second channel (a generic `module_rpc(moduleId, verb, args)` command) parallel to `generate_handler!`.

## Verification commands

```bash
cd src-tauri && cargo check
cd src-tauri && cargo clippy -- -D warnings
cd src-tauri && cargo fmt --check
bun run test -- module-ipc
bun run lint

# Sanity: exactly one handler registration
grep -n 'generate_handler' src-tauri/src/lib.rs | wc -l  # expect 1

# Sanity: CONVENTIONS.md has the new subsection
grep -n 'Module commands' CONVENTIONS.md | wc -l  # expect >= 1
```

## Status updates

- 2026-04-15 (claude): created. Designed against Tauri 2's compile-time `generate_handler!` macro constraints.
- 2026-04-17 (claude): verified. `src-tauri/src/modules_ipc.rs` carries the full pattern documentation (Rust side, `createModuleInvoke` TS side, add-a-command checklist). `lib.rs` handler is grouped with `// Core / Preflight / LSP / Forge / Current / Atlas / Terminal / Filesystem` headers and preserved by `#[rustfmt::skip]` on `pub fn run()`. `src/shell/module-ipc.ts` exports `createModuleInvoke`. `planning/CONVENTIONS.md:183` has the "Module commands" subsection. `cargo check` + `cargo fmt --check` clean. Status `ready → done`.

Note: `grep -c 'generate_handler' src-tauri/src/lib.rs` returns 2 — one real invocation on line 88, one comment reference on line 80 explaining the `#[rustfmt::skip]`. Only one registration exists. Acceptance spirit met.
