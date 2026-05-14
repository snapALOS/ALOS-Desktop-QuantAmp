---
rfc: 0004
title: Agent approval UI contract
status: accepted
author: claude
created: 2026-04-15
accepted: 2026-04-15
supersedes: null
---

# RFC 0004 — Agent approval UI contract

## Summary

Lock a single approval pipeline used by every module for any `risk: "high"` tool call. Central backend queue (`~/.alos/core/approvals.sqlite`), uniform payload shape, one shared UI surface (notification dock + dedicated pane), pluggable per-module detail renderers. Replaces the implicit "each module builds its own modal" default.

## Motivation

v0.2 introduces multiple sources of user-approval requests:

- Forge: `forge_apply_diff` (agent wants to change a file), `forge_run_command` (agent wants to run shell).
- Current: `current_trigger_workflow` when invoked by an agent (chain of side effects), and workflow `approval_gate` steps.
- Atlas: largely read-only — rare approval cases (e.g., "re-index a workspace outside the currently-open one").

Without a shared pipeline:
1. Three UI components get built, each slightly different.
2. Approvals are lost across app restart.
3. No uniform audit.
4. Agents can't deterministically await approval — each module invents its own blocking mechanism.

Locking the pipeline here means every future module inherits the surface without re-designing it.

## Proposal

### Decision 1 — Single approval queue (SQLite)

All approvals pass through one store: `~/.alos/core/approvals.sqlite`, owned by the ALOS core (not a module). Schema:

```sql
CREATE TABLE approvals (
  id TEXT PRIMARY KEY,              -- uuidv4
  created_at TEXT NOT NULL,          -- ISO 8601
  expires_at TEXT NOT NULL,
  resolved_at TEXT,                  -- NULL while pending
  status TEXT NOT NULL,              -- pending | approved | denied | timeout | cancelled
  source_module TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  source_risk TEXT NOT NULL,         -- low | medium | high | critical
  summary TEXT NOT NULL,             -- one-line human-readable
  detail_json TEXT NOT NULL,         -- module-specific payload
  context_json TEXT,                 -- { agentId?, workflowRunId?, conversationId? }
  actor TEXT                         -- user handle or 'timeout' when resolved
);

CREATE INDEX approvals_status_idx ON approvals(status);
CREATE INDEX approvals_created_idx ON approvals(created_at);
```

The queue is owned by a Python service in `backend/src/core/approvals/` (new subpackage). Modules consume it via a helper; they never touch the SQLite directly.

### Decision 2 — Uniform payload shape

```typescript
// src/contracts/approvals.ts
export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'denied'
  | 'timeout'
  | 'cancelled';

export interface ApprovalRequest {
  id: string;
  createdAt: string;          // ISO 8601
  expiresAt: string;
  source: {
    module: string;           // 'forge' | 'current' | 'atlas' | ...
    tool: string;             // full MCP tool name, e.g. 'forge_apply_diff'
    risk: 'low' | 'medium' | 'high' | 'critical';
  };
  summary: string;            // one line, shown in the notification
  detail: unknown;            // module-specific — rendered by module's detail view
  context?: {
    agentId?: string;
    workflowRunId?: string;
    conversationId?: string;
  };
  status: ApprovalStatus;
  resolvedAt: string | null;
  actor: string | null;
}
```

Python mirror at `backend/src/core/approvals/contracts.py` (Pydantic).

`detail` is deliberately `unknown` / `Dict[str, Any]` — each module defines its own shape and registers a renderer (Decision 4).

### Decision 3 — Lifecycle and blocking helper

Python-side helper:

```python
# backend/src/core/approvals/api.py
from __future__ import annotations
from typing import Any, Dict, Literal, Optional

async def request_approval(
    *,
    source_module: str,
    source_tool: str,
    source_risk: Literal["low", "medium", "high", "critical"],
    summary: str,
    detail: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 300,
) -> ApprovalRecord:
    """Enqueue an approval request and block until the user decides,
    the timeout expires, or the request is cancelled.

    Returns the final ApprovalRecord with status in
    {approved, denied, timeout, cancelled}.
    """
```

Internally:
1. Writes a `pending` row with `expires_at = now + timeout_seconds`.
2. Publishes `core.approval.requested` event.
3. `await`s an asyncio.Event keyed by the approval id.
4. When the user (or timeout, or cancel) resolves it: the row is updated, `core.approval.resolved` event fires, the event is set, and the helper returns.

A scheduled job ticks every 10s to transition expired `pending` rows to `timeout` and fire their events.

### Decision 4 — Detail renderer registry (frontend)

Each module owns the UI for rendering its own approval details. Registration:

```typescript
// src/shell/approval-renderers.ts
export interface ApprovalDetailRenderer {
  toolName: string;   // matches source.tool
  render: (detail: unknown, context: ApprovalRequest['context']) => ReactNode;
}

const renderers = new Map<string, ApprovalDetailRenderer>();

export function registerApprovalRenderer(r: ApprovalDetailRenderer): void;
export function renderApproval(req: ApprovalRequest): ReactNode;
```

Each module's frontend, at mount, registers its renderers (similar to how modules register their route):

```typescript
// modules/forge/frontend/src/approvals.ts
registerApprovalRenderer({
  toolName: 'forge_apply_diff',
  render: (detail) => <DiffApprovalView detail={detail as DiffDetail} />,
});
registerApprovalRenderer({
  toolName: 'forge_run_command',
  render: (detail) => <CommandApprovalView detail={detail as CommandDetail} />,
});
```

Unknown tool → fallback renderer that shows the raw JSON of `detail` with a warning "No custom view for this tool."

### Decision 5 — UI surfaces

Two surfaces, both driven off the same store of pending approvals:

1. **Notification dock** — bottom-right of the window. Stacks up to 3 pending approvals as cards. Each card shows `source.module`, `summary`, a risk-colored accent, and Approve/Deny buttons. Clicking the card expands to the detail renderer. This is always visible; not confined to any module's view.

2. **Approvals pane** — accessible via a "bell" icon in the activity bar (reserved order = 98, a new built-in). Pane lists all pending approvals with full detail, plus a history view of recent resolved ones (last 100, from SQLite).

The notification dock handles the common case (approve-in-passing). The pane handles cleanup ("why am I seeing so many pending?") and audit ("what did I approve yesterday?").

### Decision 6 — No auto-approval in v0.2

v0.2 **does not** support "always allow `forge_apply_diff` for this file" or "auto-approve all low-risk tools for this agent." Every high-risk tool call asks the user each time. Rationale:
- Security/trust story must start conservative. Relaxation is additive.
- The user needs to see behavior first to know what rules they'd actually want.
- Auto-approval policies require their own RFC and UI (rule editor, scope picker, expiry).

Reserved for v0.3+.

### Decision 7 — Cancellation

An approval can be cancelled before resolution:
- By the **requester** — e.g., the agent turn was cancelled (RFC-0002 §3); the agent's wrapper calls `cancel_approval(id)` to remove it from the queue.
- By the **user** — clicking "Dismiss" on a pending card transitions to `denied` (not a separate `cancelled` status — from the user's POV, dismissing = denying).
- `cancelled` status is **internal-only** and produced by cancel_approval from the requester. It's distinguished from `denied` in audit but not in UI.

### Decision 8 — Concurrency and idempotence

- An approval `id` is a uuidv4 generated by `request_approval`. No deduplication: if an agent asks twice, the user sees two requests.
- Resolving an already-resolved approval is a no-op — returns current status without mutating.
- No cross-modal locking. Forge can have 3 pending diff approvals simultaneously; the user handles them in order.

### Decision 9 — Events (additive to the bus)

```typescript
// src/contracts/events.ts — additions
| { type: 'core.approval.requested'; request: ApprovalRequest }
| { type: 'core.approval.resolved';  id: string; status: ApprovalStatus; resolvedAt: string; actor: string | null }
| { type: 'core.approval.cancelled'; id: string; cancelledAt: string }
```

`core.approval.requested` fires on insert. `core.approval.resolved` fires on user-decision or timeout. `core.approval.cancelled` fires on programmatic cancel.

### Decision 10 — What this RFC does NOT cover

- **Delegated approval** (admin approves on behalf of user in multi-user setups) — v1.x+.
- **Approval SLA metrics / dashboards** — later.
- **Hardware-key approval** (Touch ID, YubiKey) — later.
- **Approval of composite actions** (e.g., "agent wants to do N things, approve all at once") — later; for now each tool call is its own approval.

## Alternatives considered

### A. Per-module approval flows

Let each module build its own modal. Rejected for the reasons in Motivation — fragmented UX, lost audit, duplicated code.

### B. Approval queue owned by Current

Since Current already has `approval_gate` nodes, make it the queue. Rejected: Current is optional (users may not use workflows at all). Approvals must work when Current is uninstalled or disabled. Putting the queue in core makes approvals a first-class ALOS concept.

### C. Modal (blocking) instead of notification dock

Block the whole app until the user decides. Rejected: breaks multi-tasking. A long-running Current workflow that occasionally pauses for approval would make the IDE unusable. Notification pattern lets the user keep working and resolve approvals in batches.

### D. Force the user to type a reason when denying

Rejected: friction without clear benefit. An agent logs its own reasoning about why it asked; a user's reason to deny is usually self-evident. Add if a real use case emerges.

## Impact

- **New subpackage:** `backend/src/core/approvals/` — API, SQLite store, scheduled timeout job.
- **New contracts:** `src/contracts/approvals.ts` + Python mirror.
- **New UI:** `src/shell/ApprovalDock.tsx`, `src/shell/ApprovalsPane.tsx`, `src/shell/approval-renderers.ts`.
- **Events added:** `core.approval.requested`, `core.approval.resolved`, `core.approval.cancelled` (append to `src/contracts/events.ts`).
- **Activity bar:** add a built-in `approvals` entry (order 98, icon `bell`, route `/approvals`). Amends the order table in RFC-0001; this is a non-breaking addition since 98 was unused.
- **Persistence:** new SQLite file at `~/.alos/core/approvals.sqlite`.
- **Migrations:** new file, so no migration. Schema v1 baselined with this RFC.
- **Rollback:** if this RFC proves wrong, delete `backend/src/core/approvals/`, remove contract imports, and each module's tool-gate path that triggered approval goes back to auto-approving or auto-denying depending on `max_risk`. Safe rollback.

## Open questions

- **OQ-4-1:** Should the notification dock survive window-close-to-tray? **Decision:** pending approvals notify via OS notification (macOS/Win/Linux native) when the window is hidden. If denied by OS permissions, they wait until the window is shown. Implement the native notification path as a follow-up task, not a blocker.
- **OQ-4-2:** Should the ApprovalsPane mirror as a Current workflow trigger ("on approval resolved, run workflow X")? **Decision:** yes eventually. Out of scope for v0.2; add after Current event-trigger plumbing lands.
- **OQ-4-3:** When the app is killed mid-approval (SIGKILL), the `pending` row persists. On next startup, should we promote to `timeout`? **Decision:** no — on startup, re-emit `core.approval.requested` for any `pending` rows whose `expires_at > now`. Let the normal timeout tick handle the rest. Preserves user intent across crashes.

## Decision log

- 2026-04-15 (claude): initial draft and accepted. Binds tasks 0090 (capability gates) and 0091 (approval UI implementation).
