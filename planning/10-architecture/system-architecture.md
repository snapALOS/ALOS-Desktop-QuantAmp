# System Architecture

## Top-level view

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          ALOS Desktop (Tauri shell)                       │
│                                                                           │
│  ┌────────────┐  ┌──────────────────────────────────────────────────┐    │
│  │  Activity  │  │                                                   │    │
│  │    Bar     │  │               Active Module View                  │    │
│  │  (module   │  │   (Forge editor / Current canvas / Atlas graph)   │    │
│  │  switcher) │  │                                                   │    │
│  │            │  │                                                   │    │
│  │  ▸ Forge   │  │                                                   │    │
│  │  ▸ Current │  │                                                   │    │
│  │  ▸ Atlas   │  │                                                   │    │
│  │            │  │                                                   │    │
│  │  ▸ Chat    │  │                                                   │    │
│  │  ▸ Ext.    │  │                                                   │    │
│  └────────────┘  └──────────────────────────────────────────────────┘    │
│                                                                           │
│              Tauri commands (IPC) ↕  Rust core  ↕  PyInstaller sidecar    │
└───────────────────────────────────────────┬──────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │                             │                             │
      ┌───────▼───────┐            ┌────────▼────────┐          ┌─────────▼─────────┐
      │ ALOSCurrent   │            │  Agent runtime  │          │    ALOSAtlas      │
      │ (workflow)    │  invokes   │   (LangGraph    │  queries │  (code graph +    │
      │  DAG engine   │ ─────────▶ │    supervisor)  │ ───────▶ │    MCP server)    │
      │  SQLite       │            │  Python sidecar │          │   SQLite + MCP    │
      └───────────────┘            └─────────────────┘          └───────────────────┘
                                            │
                                            │ tools
                             ┌──────────────┼──────────────┐
                             ▼              ▼              ▼
                       ┌─────────┐    ┌─────────┐    ┌───────────┐
                       │  Forge  │    │   LSP   │    │  Sandbox  │
                       │ editor/ │    │ servers │    │ (exec     │
                       │ terminal│    │         │    │ isolation)│
                       └─────────┘    └─────────┘    └───────────┘
```

## Layer responsibilities

### Shell (Tauri + React)
- Window, tray, menus, activity bar, module registry, IPC plumbing.
- Hosts module views; does **not** contain module business logic.

### Rust core (`src-tauri/src/`)
- Lifecycle: preflight, spawn sidecar, tray, shutdown.
- IPC commands: the only sanctioned channel between frontend and backend.
- Sandbox primitives (process isolation, resource limits) — consumed by modules.

### Python sidecar (`backend/src/`)
- Agent runtime (LangGraph supervisor + workers).
- Module backends that need Python (Atlas graph, Current workflow engine).
- Exposed to frontend via localhost HTTP + MCP stdio where appropriate.

### Modules (`modules/<name>/`)
- Each a **hard-isolated** package with its own manifest.
- Frontend code in `modules/<name>/frontend/`, backend in `modules/<name>/backend/`.
- Communicates with core and with other modules **only** through declared contracts (see [ipc-contracts.md](ipc-contracts.md)).
- Each module owns: its UI surface, its persistence, its API, its tests.

## Control flow examples

**Example 1 — user edits a file in Forge:**
Frontend Monaco → Forge backend → filesystem. Forge emits `file.changed` event → Atlas subscribes → incremental re-index. No other module is involved.

**Example 2 — user runs a workflow in Current:**
Frontend canvas → Current backend (DAG engine) → step types dispatched:
- `http` → stdlib http client
- `invoke_agent` → LangGraph supervisor (with scoped state)
- `shell` → sandbox
- `human_approval` → blocks on frontend task-board acknowledgment
Each step checkpoints to Current's SQLite.

**Example 3 — agent makes a refactor:**
Chat → supervisor → coder agent → **Atlas.impact(symbol)** tool → **LSP.references(symbol)** tool → proposes diff → frontend diff view → user accepts → Forge applies → Atlas re-indexes.

## Why this topology

- **Current sits above LangGraph**, not instead of it. Current is for cross-time, cross-module orchestration; LangGraph is for within-conversation agent turns.
- **Atlas is a tool, not a participant.** Agents call it; it does not decide.
- **Modules don't import each other.** They consume declared events and IPC commands. Removing one module must not break another at compile time.
- **The sidecar is singular.** All Python code lives in one process to avoid triple-PyInstaller bloat. Module isolation is at the package level, not process level.

## What v0.2 does NOT do

- No multi-process module isolation.
- No module hot-reload.
- No cloud/remote modules.
- No module marketplace.

These are v0.3+ concerns and are deliberately excluded to keep v0.2 shippable.
