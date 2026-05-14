# IPC Contracts

**One rule:** if two pieces of code talk, they talk through a file under `contracts/`. No exceptions.

## Channels

ALOS has four IPC channels. Each has its own contract style.

### 1. Tauri commands (frontend ↔ Rust core)

Defined in `src-tauri/src/<area>.rs` with `#[tauri::command]` and invoked from the frontend via `invoke('name', { args })`.

**Contract location:** `src/contracts/tauri-commands.ts` — hand-authored TypeScript signatures matching the Rust functions.

**Naming:** snake_case Rust → camelCase TS invoke. One command per Rust function. Never overload.

**Example:**
```rust
// src-tauri/src/backend.rs
#[tauri::command]
pub fn backend_status() -> BackendStatus { ... }
```
```typescript
// src/contracts/tauri-commands.ts
export interface BackendStatus { running: boolean; pid: number | null; }
export const backendStatus = () => invoke<BackendStatus>('backend_status');
```

### 2. HTTP (frontend ↔ Python sidecar)

The sidecar binds to `127.0.0.1:<port>` (port in `~/.alos/runtime.json`). Routes are namespaced by module.

**Routes:**
- `/api/core/*` — core sidecar routes (health, shutdown, routing).
- `/api/forge/*` — Forge backend.
- `/api/current/*` — Current backend (DAG engine API).
- `/api/atlas/*` — Atlas backend (graph queries).

**Contract location:** `modules/<name>/contracts/http.ts` — OpenAPI-flavored TS types (request/response shapes) per route.

**Rules:**
- Every response has `{ ok: boolean, data?, error? }` envelope.
- Errors always include `code: string` (machine-readable) and `message: string` (human-readable).
- No route answers > 5 MB synchronously; stream instead.

### 3. Event bus (any ↔ any, pub/sub)

Events are the only permitted way for two modules to influence each other without direct coupling.

**Contract location:** `src/contracts/events.ts` — discriminated union of all event types.

```typescript
// src/contracts/events.ts
export type AlosEvent =
  | { type: 'forge.file.changed'; path: string; timestamp: number }
  | { type: 'forge.file.saved'; path: string; timestamp: number }
  | { type: 'atlas.index.started'; root: string }
  | { type: 'atlas.index.complete'; root: string; symbols: number }
  | { type: 'current.workflow.started'; workflowId: string; runId: string }
  | { type: 'current.workflow.completed'; runId: string; status: 'ok' | 'error' }
  | { type: 'agent.turn.started'; conversationId: string; agentId: string }
  | { type: 'agent.turn.completed'; conversationId: string; agentId: string; tokens: number };
```

**Rules:**
- Event names are dot-namespaced: `<module>.<subject>.<verb>`.
- Payloads are **additive only** across versions (never remove or retype a field post-ship).
- Events are fire-and-forget. A publisher does not know or care who subscribes.
- No event may trigger an event synchronously (no fan-out storms); subscribers must queue.

### 4. MCP tools (agent ↔ module)

Agents see module capabilities as MCP tools. Each module that exposes agent-facing capabilities ships an MCP server (stdio-attached child of the sidecar).

**Contract location:** `modules/<name>/contracts/mcp.py` — `@mcp.tool()` signatures + JSON schemas.

**Rules:**
- Tool names are `<module>_<verb>_<subject>`: `atlas_impact_symbol`, `forge_open_file`, `current_trigger_workflow`.
- Every tool has a capability gate (see `backend/src/agents/capabilities.py`).
- Destructive tools (write, delete, exec) are marked `risk: "high"` and require approval in the frontend.

## Versioning

Each contract file has a header:
```typescript
// CONTRACT VERSION: 2
// LAST CHANGED: 2026-04-15
// BREAKING CHANGES ALLOWED THROUGH: v0.x. LOCKED at v1.0.
```

Incrementing the version number requires an RFC if the change removes or retypes anything.

## Where things are NOT allowed to talk

- Frontend module code may not `fetch()` directly; use the contract layer. (Lint rule.)
- Python module code may not `import` another module's internals (see [module-boundaries.md](module-boundaries.md)).
- Two modules may not share a SQLite connection.
