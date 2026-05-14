---
rfc: 0001
title: Module registry and activity bar contract
status: accepted
author: claude
created: 2026-04-15
accepted: 2026-04-15
supersedes: null
---

# RFC 0001 — Module registry and activity bar contract

## Summary

Lock down exactly how modules are discovered at startup, how the activity bar (narrow left nav) renders them, and how frontend and Rust agree on the registry. This decision unblocks tasks 0002 (activity bar), 0004 (MODULE.toml loader), and every module mount task.

## Motivation

Three modules land in v0.2 (Forge, Current, Atlas). Two more (Cortex, Reflex) are architecturally reserved. Plus three built-ins (Chat, Extensions, Settings). Without a contract, each module task re-decides:

- Who scans `MODULE.toml`?
- What happens when a MODULE.toml is malformed?
- How do built-ins mix with discovered modules?
- What are the ordering rules?
- What does "unavailable" look like?
- How is the active module persisted?
- Where do icons come from?

Six unresolved questions × three agents → chaos. This RFC answers them all.

## Proposal

### Decision 1 — Single source of truth: Rust

The Rust core scans `modules/*/MODULE.toml` at startup and exposes the merged list (built-ins + discovered) via a single Tauri command. The frontend never touches the filesystem to discover modules.

**Why Rust, not frontend:** the TOML loader is already being built in Rust (task 0004). The frontend already consumes Rust-authored state through `invoke`. Duplicating discovery would create two sources of truth and the "why don't my modules match?" bug.

**API:**

```rust
// src-tauri/src/modules.rs
#[tauri::command]
pub fn list_modules() -> Vec<ModuleEntry>
```

```typescript
// src/contracts/tauri-commands.ts
export interface ModuleEntry {
  id: string;                    // e.g. 'forge', 'chat', 'settings'
  displayName: string;           // e.g. 'ALOSForge', 'Chat'
  version: string;
  order: number;                 // 1..99 modules; 90..99 reserved for built-ins
  icon: string;                  // lucide-react icon name, e.g. 'code', 'message-square'
  route: string;                 // e.g. '/forge', '/chat'
  available: boolean;            // false if load failed
  errorMessage: string | null;   // populated when available === false
  kind: 'module' | 'builtin';
}

export const listModules = () =>
  invoke<ModuleEntry[]>('list_modules');
```

### Decision 2 — Built-ins are baked into Rust

Built-ins (`chat`, `extensions`, `settings`) are **not** represented as MODULE.toml files under `modules/`. They are hardcoded in the Rust registry and merged into the output of `list_modules`. This keeps the `modules/` directory reserved for real, hard-isolated modules.

```rust
// src-tauri/src/modules.rs
fn builtin_entries() -> Vec<ModuleEntry> {
    vec![
        ModuleEntry {
            id: "chat".into(),
            display_name: "Chat".into(),
            version: env!("CARGO_PKG_VERSION").into(),
            order: 90,
            icon: "message-square".into(),
            route: "/chat".into(),
            available: true,
            error_message: None,
            kind: ModuleKind::Builtin,
        },
        ModuleEntry {
            id: "extensions".into(),
            // ... order 95, icon 'puzzle', route '/extensions'
        },
        ModuleEntry {
            id: "settings".into(),
            // ... order 99, icon 'settings', route '/settings'
        },
    ]
}
```

### Decision 3 — Order reservation

| Range | Use |
|---|---|
| `1..=9` | Primary workflow modules (Forge=10 is in the next band; we leave 1–9 for a future "home"/"welcome" module) |
| `10..=49` | User-facing product modules. Forge=10, Current=20, Atlas=30, Cortex=40 (reserved), Reflex=50 (reserved, lives in the next band) |
| `50..=89` | Secondary / utility modules (none yet; reserved) |
| `90..=99` | Built-ins |

Concrete assignments for v0.2:

| Module | order |
|---|---|
| Forge | 10 |
| Current | 20 |
| Atlas | 30 |
| Cortex *(hidden)* | 40 |
| Reflex *(hidden)* | 50 |
| Chat | 90 |
| Extensions | 95 |
| Settings | 99 |

**Collision rule:** if two entries have identical `order`, deterministically break ties by `id` ascending, and log a `WARNING` naming both modules. No crash.

### Decision 4 — Hidden modules

Cortex and Reflex have reserved `order` values but are not rendered in the activity bar for v0.2. The registry exposes a `hidden: boolean` field (default `false`). Hidden entries are filtered from the UI render but remain in the registry for type stability.

Add this field:

```typescript
hidden: boolean; // if true, present in registry but not in activity bar
```

v0.2 built-ins and shipped modules all have `hidden: false`. Cortex/Reflex, when their entries are added to the registry in a later version, can be `hidden: true` until they ship.

**For v0.2, we do not create MODULE.toml entries for Cortex/Reflex.** The type is stable; the data is absent. Adding them later is additive.

### Decision 5 — Icons: lucide name strings

The `icon` field is a **string** naming a lucide-react icon (e.g. `"code"`, `"workflow"`, `"network"`). The frontend translates strings to components via a small mapping in `src/shell/icon-map.ts`. Unknown icon names render `HelpCircle` and log a warning.

Rationale: keeps MODULE.toml language-agnostic; no SVG bundling per module; icon rotation requires zero code changes (just edit MODULE.toml).

### Decision 6 — Unavailable module rendering

If a module's MODULE.toml fails to parse or its declared entrypoint is missing, the Rust loader returns the entry with `available: false` and a human-readable `errorMessage`.

**UI behavior:**

- Icon rendered at 50% opacity with `cursor: not-allowed`.
- Tooltip on hover: `"<DisplayName> — unavailable. Click for details."`
- Click opens a modal (`src/shell/ModuleUnavailableModal.tsx`) showing:
  - The module id and display name.
  - The full `errorMessage`.
  - A button "Open module folder" that invokes `reveal_in_finder(modulePath)` (deferred — can ship as a no-op button in v0.2).
  - A button "Retry" that invokes `refresh_modules()` and re-renders the activity bar.

Unavailable modules **cannot** be set as the active module programmatically. Attempting to do so logs an error and falls back to Chat.

### Decision 7 — Active module persistence

The active module is persisted in a Zustand store backed by `localStorage`, key `alos:active-module`. On app load:

1. Registry loads.
2. Store reads `localStorage` for last active.
3. If that id exists in registry AND is `available: true` AND `hidden: false`, activate it.
4. Otherwise activate `chat` (always-available builtin).

```typescript
// src/store/active-module.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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
    { name: 'alos:active-module' },
  ),
)
```

**Note:** Zustand's `persist` middleware is already usable via the existing zustand dep. No new dependency needed.

### Decision 8 — Badges (contract only for v0.2)

Each module may publish a badge value (a number or a dot) via the event bus:

```typescript
// in src/contracts/events.ts — addition
| { type: 'module.badge.set'; moduleId: string; badge: number | 'dot' | null }
```

The activity bar subscribes and renders:
- Number (>99 shown as `99+`) as a small pill on the icon.
- `'dot'` as a 6px dot (unread indicator, no count).
- `null` clears the badge.

**v0.2 rule:** contract is wired; no module publishes badges yet. Implementation lands task-by-task as modules need it. Current is the first candidate (show running workflow count).

### Decision 9 — Keyboard shortcuts

`Cmd/Ctrl+1..9` activates the Nth visible module in order. Uses `react-hotkeys-hook` only if it's already a dep — otherwise hand-rolled listener in the activity bar component. **Do not add a new dep.**

Hidden and unavailable entries are skipped when numbering — `Cmd+1` is always the first visible entry, not the first registry entry.

### Decision 10 — What the registry does NOT do in v0.2

- **No hot-reload.** Registry is frozen at app startup. `refresh_modules` only re-scans but requires a modal prompt to tell the user to refresh if anything changed.
- **No user-configurable order.** The `order` from MODULE.toml is authoritative.
- **No module install/uninstall UI.** Modules ship with the app.
- **No right-click context menu** on icons.
- **No drag-to-reorder.**

All of the above are v0.3+ concerns, deliberately out of scope.

## Alternatives considered

### A. Frontend-only registry via Vite glob import

`import.meta.glob('./modules/*/MODULE.toml')`. Rejected because:
- Requires TOML parsing in the browser (extra dep).
- Breaks down for modules that need Rust-side lifecycle (LSP supervisor, pty management) — they'd need a second registration mechanism.
- Two sources of truth = two failure modes.

### B. JSON instead of TOML for MODULE manifests

TOML matches the existing `tauri.conf.json` → `Cargo.toml` mix in the repo and is friendlier for hand-editing. Cost-neutral in parsing difficulty. Keeping TOML.

### C. One big `manifest.toml` at repo root listing all modules

Rejected. Violates module self-containment (you can't `rm -rf modules/foo/` without also editing a top-level file). Contradicts [module-boundaries.md](../10-architecture/module-boundaries.md).

### D. Database-backed registry

Overkill for v0.2. Filesystem scan + in-memory cache is fine.

## Impact

- **Contracts touched:**
  - `src/contracts/tauri-commands.ts` — adds `ModuleEntry`, `listModules`, `refreshModules` exports.
  - `src/contracts/events.ts` — adds `module.badge.set` variant.
- **Files introduced:**
  - `src-tauri/src/modules.rs` (task 0004).
  - `src/shell/module-registry.ts`, `ActivityBar.tsx`, `ModuleShell.tsx` (task 0002).
  - `src/shell/icon-map.ts`.
  - `src/store/active-module.ts`.
  - `src/shell/ModuleUnavailableModal.tsx`.
- **Migrations:** none (no existing registry to migrate).
- **Rollback:** if this contract proves wrong, affected files are all new — delete the shell directory and the modules.rs to revert. No cascading damage.

## Open questions

- **OQ-1:** How do we handle MODULE.toml files whose `requires` list references a module that isn't installed? (v0.2: all required modules are shipped — defer.) Resolution target: RFC on inter-module dependencies when the first optional-dep appears. Owner: whoever files the follow-up task.
- **OQ-2:** Do built-in entries get versioning independent of the app? (v0.2: they inherit `CARGO_PKG_VERSION`.) Revisit at v1.0.
- **OQ-3:** `reveal_in_finder` cross-platform parity (Windows Explorer, Linux `xdg-open`). Deferred; button is hidden in v0.2 if cross-platform isn't ready.

## Decision log

- 2026-04-15 (claude): initial draft and accepted. No prior decisions contradicted.
