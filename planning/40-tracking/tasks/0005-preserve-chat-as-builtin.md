---
id: 0005
title: Preserve v0.1 Chat surface as a built-in registry entry
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: m
blocks: []
blocked_by: [0002, 0004]
related_rfc: 0001
pr: null
---

# 0005 — Preserve v0.1 Chat surface as a built-in registry entry

## Context

ALOS v0.1 renders a single surface: the agent chat. In v0.2 this surface becomes one of several modules reachable from the activity bar. Chat is **not** a module (no `modules/chat/` directory, no MODULE.toml) — it's a built-in registry entry whose implementation lives in the shell code that already exists.

This task refactors the existing shell to render chat through the module slot, preserving every v0.1 behavior (sessions, message history, auth gates, setup flow). It is a pure refactor — no feature changes.

See [RFC-0001](../../30-rfcs/0001-module-registry-and-activity-bar.md) §Decision 2 (built-ins baked into Rust) and §Decision 7 (active module persistence).

## Scope

**In scope:**
- Make the `chat` entry appear in the activity bar's registry output (via the Rust built-in list from task 0004).
- Refactor `src/App.tsx` so the `ChatView` renders only when `activeModuleId === 'chat'`, through the `ModuleShell` component from task 0002.
- Ensure the preflight / setup / login gates from v0.1 still run before the activity bar appears. The activity bar is inside `AppShell`, so the gates precede it — which matches v0.1 ordering.
- Keep `ChatView`, `AppShell`, and all existing chat-related components at their current paths. Do **not** move them to `modules/chat/`.
- When `activeModuleId` is any other id (e.g. `'extensions'`, `'settings'`), render a placeholder view "Module not yet implemented" for v0.2. Real module views land in their own tasks.

**Out of scope:**
- Extracting chat into a real module. Chat stays built-in in v0.2 and beyond.
- Refactoring anything inside `ChatView` itself.
- Implementing the Extensions or Settings surfaces (separate tasks if/when written).
- Visual changes to chat beyond what fitting inside the module slot demands.

## Files to touch

- `src/App.tsx` — wrap post-auth render in `<AppShell><ModuleShell /></AppShell>`, where `ModuleShell` dispatches on the active module id.
- `src/components/layout/AppShell.tsx` — render the activity bar on the left and the module slot as children. Inspect existing structure first; minimize unrelated changes.
- (NEW) `src/shell/ModuleShell.tsx` — delivered in task 0002; this task consumes it.
- (NEW) `src/shell/module-views.tsx` — a small dispatcher that maps `moduleId → React element`. Exports a `defaultRenderFor(moduleId)` that `ModuleShell` uses.
  - `chat` → `<ChatView />`
  - `extensions` → `<ExtensionsPlaceholder />`
  - `settings` → `<SettingsPlaceholder />`
  - any other id → `<ModulePlaceholder moduleId={id} />`
- (NEW) `src/shell/ExtensionsPlaceholder.tsx` — single-screen copy: "Extensions panel — preserved in v0.2. Hardcoded demos will appear here in a follow-up task."
- (NEW) `src/shell/SettingsPlaceholder.tsx` — for now, pass-through to a minimal settings surface; do NOT re-implement settings in this task (flag it in the body).
- (NEW) `src/shell/ModulePlaceholder.tsx` — "This module is installed but not yet rendered. Module id: <id>."
- (NEW) `src/store/active-module.ts` — Zustand store per RFC-0001 §Decision 7. Persist with `zustand/middleware/persist`.

## Acceptance criteria

- [ ] Launching the app from a clean state lands on the Chat view after auth, identical to v0.1 behavior.
- [ ] The activity bar is visible with at least the three built-in icons (chat, extensions, settings).
- [ ] Clicking the Chat icon shows `ChatView`. Message send/receive still works. Sessions list still works. Nothing regresses against v0.1.
- [ ] Clicking the Extensions icon shows the placeholder page.
- [ ] Clicking the Settings icon shows the placeholder page (not a broken screen).
- [ ] Killing and reopening the app lands on whichever module was last active (persistence via `alos:active-module` localStorage key).
- [ ] Manually editing localStorage to an unknown id falls back to Chat on next load.
- [ ] No file was moved into `modules/chat/`. Grep: `find modules -type d -name chat | wc -l` returns `0`.
- [ ] `bun run lint` passes. `bun run build` passes.
- [ ] v0.1 chat integration tests (if any exist) still pass.

## Implementation notes

- Read `src/App.tsx` end to end before changing anything. The existing state machine (preflight / backend / setup / login / ready) is a valuable design; preserve its order.
- The activity bar is inside `AppShell` — do not duplicate the gates above it. Gates stay where they are.
- If you find an existing settings or extensions surface (grep `src/components/` for clues), use it instead of the placeholder. Don't reinvent.
- Zustand's `persist` middleware needs hydration handling: check if the persisted value is valid against the current registry. The validation goes inside the component reading the active id, not the store itself — the store stays schema-free.
- Keyboard shortcut `Cmd/Ctrl+1` should land on the first visible module (currently Forge after Forge lands; until then, Chat). Don't hardcode.

## Verification commands

```bash
bun run lint
bun run build
bun run dev    # manual: launch, auth, see activity bar, click through entries
```

Grep checks:
```bash
find modules -type d -name chat | wc -l        # expect 0
grep -rn 'ChatView' modules/ 2>/dev/null | wc -l  # expect 0 — Chat is built-in
```

## Status updates

- 2026-04-15 (claude): created. See RFC-0001 for the registry contract this task consumes.
- 2026-04-17 (claude): verified. Chat registered as built-in in `src-tauri/src/modules.rs` (`id: "chat"`, `order: 90`, `route: "/chat"`). `src/shell/module-views.tsx` dispatches `case 'chat' → <ChatView />`. `src/store/active-module.ts` persists selection via Zustand. `ls modules/chat` → no such directory (Chat stays built-in, not vendored). Status `ready → done`.
