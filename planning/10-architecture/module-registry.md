# Module Registry & Activity Bar

**Contract locked by [RFC-0001](../30-rfcs/0001-module-registry-and-activity-bar.md).** This doc is the reader-friendly overview; the RFC is the authoritative spec with decisions, alternatives, and open questions.

## What the user sees

A narrow (~48px) vertical bar on the far left of the ALOS window, VS Code style. Each icon switches the main view to that module. Icons are grouped:

```
┌─────┐
│ ▸ F │  Forge     (editor)
│ ▸ C │  Current   (workflows)
│ ▸ A │  Atlas     (code graph)
├─────┤
│ ▸ 💬│  Chat      (agent chat — existing v0.1 surface, preserved)
│ ▸ 🧩│  Extensions (hardcoded demo data for v0.2)
├─────┤
│     │  (future: Cortex, Reflex slots reserved but hidden until shipped)
├─────┤
│ ▸ ⚙ │  Settings
└─────┘
```

## Registry contract

The registry is a typed list loaded at shell startup. Each entry comes from a module's `MODULE.toml`.

```typescript
// src/shell/module-registry.ts
export interface ModuleEntry {
  id: 'forge' | 'current' | 'atlas' | 'chat' | 'extensions' | 'settings';
  displayName: string;
  icon: string;         // name of a lucide icon
  route: string;        // '/forge', '/current', etc.
  order: number;        // sort key
  available: boolean;   // false → grayed out, click for error details
  errorMessage?: string;
}
```

The registry is populated by:
1. **Static built-ins:** `chat`, `extensions`, `settings` (always present).
2. **Module scan:** read each `modules/*/MODULE.toml` and append.

Modules that fail to load still appear with `available: false` so the user can see what's broken instead of silently missing features.

## Nav-bar state rules

- **Active module:** highlighted (accent border on left edge, icon color shift).
- **Badge:** each icon may show a numeric/dot badge driven by the module (e.g., Current shows running workflow count, Atlas shows indexing status).
- **Keyboard:** `Cmd/Ctrl+1`..`Cmd/Ctrl+9` switches by order.
- **Secondary nav:** the module's own sidebar (file tree for Forge, workflow list for Current, etc.) renders to the right of the activity bar, inside the module view. The activity bar only switches modules.

## Module view mount/unmount

- On first switch to a module, its frontend mounts lazily (code-split bundle).
- On switch away, module frontend **stays mounted but hidden** (state preservation) until memory pressure or explicit close.
- Module backends (Python) are always warm for v0.2 (single-sidecar model).

## Adding a module (recipe)

1. Create `modules/<name>/` with the layout in [module-boundaries.md](module-boundaries.md).
2. Write `MODULE.toml` with unique `id`, `route`, and an `order` that doesn't collide.
3. Export contracts from `contracts/`.
4. Implement backend in `backend/src/alos_<name>/` and frontend in `frontend/src/`.
5. Write an RFC in `30-rfcs/` if the module introduces new cross-module events or commands.
6. Add a task file in `40-tracking/tasks/` for the integration.

No registration step required beyond the scan — the shell discovers the module from `MODULE.toml`.

## Reserved but hidden slots

Cortex (order 40) and Reflex (order 50) are reserved in the type union but hidden from the nav until they ship. This keeps types stable across versions.
