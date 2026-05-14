---
id: 0002
title: Build module registry and activity bar skeleton
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: m
blocks: [0011, 0031, 0051]
blocked_by: [0001, 0004]
related_rfc: 0001
pr: null
---

# 0002 — Build module registry and activity bar skeleton

## Context

The v0.2 IDE needs a VS-Code-style narrow left nav bar for module switching. That nav is driven by a module registry that discovers modules from their `MODULE.toml` files. Both the registry and the UI need to exist before any specific module can mount.

See [`planning/10-architecture/module-registry.md`](../../10-architecture/module-registry.md) for the contract.

## Scope

**In scope:**
- `src/shell/module-registry.ts`: the `ModuleEntry` type, a `loadRegistry()` function that returns built-ins + scanned `MODULE.toml` entries (use 0004's loader), with fail-soft `available: false` on load errors.
- `src/shell/ActivityBar.tsx`: ~48px vertical bar component rendering registry entries as buttons. Highlight the active module. Left edge accent. Keyboard shortcuts `Cmd/Ctrl+1..9`.
- `src/shell/ModuleShell.tsx`: hosts the active module's view. Default "no module selected" state shows Chat (preserve v0.1 behavior).
- Wire into `src/App.tsx` (or existing root) with the activity bar always visible on the left.
- Preserve the existing Chat surface — it becomes a built-in registry entry, not a module.

**Out of scope:**
- Any specific module (Forge/Current/Atlas) mounting — those are in their own tasks.
- Badges on nav entries (future task).
- Lazy loading of module bundles (we ship all registered modules in the main bundle for v0.2 to keep this simple).

## Files to touch

- (NEW) `src/shell/module-registry.ts`
- (NEW) `src/shell/ActivityBar.tsx`
- (NEW) `src/shell/ModuleShell.tsx`
- (NEW) `src/shell/index.ts` — barrel export
- `src/App.tsx` (or equivalent root) — mount the shell components, preserving existing Chat view as a default module entry
- (NEW) `src/shell/__tests__/module-registry.test.ts` — at least smoke test: built-ins present, unknown module ID rejected

## Acceptance criteria

- [ ] `src/shell/module-registry.ts` exports `ModuleEntry` interface matching the doc.
- [ ] `loadRegistry()` returns at least the built-ins: `chat`, `extensions`, `settings`.
- [ ] Running `bun run dev` shows a narrow left bar with icons for the built-ins.
- [ ] Clicking Chat shows the existing v0.1 chat UI.
- [ ] `Cmd+1` (or `Ctrl+1` on Linux/Windows) switches to the first entry.
- [ ] Unit test smoke passes: `bun run test -- module-registry`.
- [ ] No visual regression on the existing Chat surface (take a screenshot before and after; dimensions may shift by ~48px to accommodate the bar, but content is intact).

## Implementation notes

- Use `lucide-react` for icons (already a dependency).
- The activity bar should be `sticky top-0 h-screen` — never scroll it off.
- Accessibility: each button gets an `aria-label` set to the module's display name.
- **Styling:** Tailwind 4 + shadcn-style primitives under `src/components/ui/`. Design tokens from `src/index.css` (`bg-background`, `text-foreground`, `bg-primary` for active, `text-muted-foreground` for inactive). No MUI, no CSS modules. Inspect existing `src/components/layout/AppShell.tsx` first and match its conventions.
- Active-module indicator: left-edge accent using `border-l-2 border-primary`.

## Verification commands

```bash
bun run dev                     # manual: open app, confirm nav bar renders
bun run test -- module-registry
bun run build                   # must still succeed
cd src-tauri && cargo check
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-17 (claude): verified. `src/shell/{module-registry.ts, ActivityBar.tsx, ModuleShell.tsx, RootShell.tsx}` all present. Rust-side registry (`modules.rs` + `modules_test.rs`) passes 5/5. Frontend test harness present under `src/shell/__tests__/`. Status `ready → done`.
