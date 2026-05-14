---
rfc: 0005
title: Event bus delivery semantics
status: accepted
author: claude
created: 2026-04-15
accepted: 2026-04-15
supersedes: null
---

# RFC 0005 — Event bus delivery semantics

## Summary

Lock what the event bus actually guarantees across the Python ↔ Rust ↔ frontend processes: delivery, ordering, backpressure, payload limits, subscription lifecycle. Binds task 0003 (event bus implementation) and every publisher/subscriber after it.

## Motivation

The event bus is the only permitted way for two modules to influence each other. Everything downstream — Current triggers, Atlas re-indexing on save, Monitor tab streams, activity bar badges — depends on its semantics. Left underspecified, we get three subtly incompatible implementations in three modules and race conditions that are painful to debug.

This RFC sets expectations so publishers know what they can rely on and subscribers know what they need to handle defensively.

## Proposal

### Decision 1 — Best-effort delivery (no guarantees)

The bus is **best-effort**. A subscriber that is unavailable at the moment an event is published **does not** receive that event later. No replay, no persistent queue, no delivery receipts.

Implications:
- New subscribers do not get historical events. They see only events published from the moment they subscribe onward.
- A process that restarts does not recover missed events.
- Modules that need reliable state must derive it from a persistent source (SQLite rows, filesystem scan), not from observed events.

Events are for **signaling**, not for **data transfer**. "Atlas finished indexing — go check" is correct. "Here is the complete symbol list in the payload" is wrong (see Decision 6).

### Decision 2 — In-process ordering preserved; cross-process ordering is not

Within a single process (Python sidecar, or frontend webview), events are dispatched in the order they were published. `publish(A); publish(B)` → every in-process subscriber sees A before B.

**Across processes, ordering is not guaranteed.** Events published by Python and events published by the frontend may arrive at a common subscriber (e.g., Rust core) in either order, depending on IPC scheduling.

If a subscriber cares about order of events from different processes, it must sort using the `timestamp` field (Decision 7).

### Decision 3 — No backpressure. Slow subscribers drop events.

The bus does **not** pause publishers for slow subscribers. If a subscriber's handler is still running when the next event arrives for it, the bus:

1. Queues the event up to an implementation-defined bound (`MAX_PENDING_PER_SUBSCRIBER = 256`).
2. If the bound is exceeded, drops the **oldest** pending event for that subscriber.
3. Logs a WARN per drop: `"event_bus: dropped oldest pending event for subscriber <id>; check for slow handler"`.

Subscribers must be fast. Long work belongs in a thread/worker triggered from the handler, not in the handler itself.

### Decision 4 — Subscription lifecycle is manual

- Subscribing returns an unsubscribe callable. Components must call it on teardown.
- No automatic GC-based cleanup. Subscriptions outlive the object that created them until explicitly unsubscribed.
- React hook pattern (mandatory in all frontend subscribers):
  ```typescript
  useEffect(() => {
    const unsub = bus.subscribe('forge.file.saved', handler);
    return unsub;
  }, [bus, handler]);
  ```
- Python pattern:
  ```python
  unsub = bus.subscribe("forge.file.saved", handler)
  try:
      ...
  finally:
      unsub()
  ```

### Decision 5 — Exact-type-string subscription only

`bus.subscribe('forge.file.saved', handler)` matches that exact event type. No wildcards (`'forge.*'`), no regex. Rationale:
- Predictable matching. No "why is my handler firing for this unrelated event?" debugging.
- Adding a new event variant never accidentally activates a subscriber.
- If a subscriber truly needs all events under a prefix, it subscribes to each variant explicitly, or — in rare cases — subscribes to a `'*'` meta-type the bus exposes only for debug tools.

Deferred to v0.3 if a real use case emerges.

### Decision 6 — Payload size limit

A single event payload must be **≤ 64 KB** when serialized as JSON. The bus enforces this by measuring the serialized length before dispatch; oversize events are rejected with a thrown error at `publish()` time (not silently dropped — this is publisher programming error, not runtime condition).

Events are signals, not transports. If you have > 64 KB of data to communicate:
- Write it to disk or SQLite.
- Publish an event whose payload is a **reference** (file path, DB row id).
- Subscribers pull the data.

Rationale: keeps cross-process IPC cheap, limits memory pressure, surfaces design drift early ("your events shouldn't be carrying file contents").

### Decision 7 — Every event carries a timestamp

Every event — regardless of type — has a `timestamp: number` field (Unix milliseconds since epoch, source process's clock). The bus does not inject it; publishers set it.

This is already implied by every event type we've specced (most include `timestamp` explicitly; retrofit the few that don't). Subscribers that need cross-process ordering sort on it.

### Decision 8 — Synchronous in-process dispatch; asynchronous cross-process

- **In-process (same runtime):** handlers are called synchronously, in the same tick of the event loop, in subscription-registration order. All handlers for event A complete before event B's dispatch begins.
- **Cross-process:** marshalling through Tauri `emit`/`listen` and the Python ↔ Rust bridge is asynchronous. Timing depends on IPC scheduling. No ordering guarantees as above.

### Decision 9 — No synchronous event chaining inside handlers

A handler must **not** call `bus.publish()` inline within its own execution. Such calls are detected and deferred to the next event-loop tick (frontend) or queued and dispatched by the bus's own thread (Python) — they don't throw, but they never execute synchronously.

Rationale: prevents reentrancy. "Handler of A publishes B, whose handler publishes A" becomes a legal loop bug; the async defer breaks the cycle into discrete ticks the developer can reason about.

Handlers that genuinely need to fire a downstream event should use a small helper: `bus.publishLater(event)` which enqueues. `publish` inside a handler is auto-routed to `publishLater` with a DEBUG log.

### Decision 10 — No persistence, no audit

The bus does **not** persist events. No built-in audit. Modules that want audit roll their own:
- Current persists workflow-step events to `execution_steps` (already does).
- A future debug tool could subscribe to `*` and persist to a ring buffer for diagnostics. Not a bus concern.

Rationale: keeping the bus slim means all three implementations (Python, Rust, frontend) stay small and obvious. Cross-cutting audit at the transport level tends to grow features forever.

### Decision 11 — Cross-process bridge topology

```
Python publisher ──┐                             ┌── Python subscriber
                   │                             │
           ┌───────▼──────────┐    ┌─────────────▼──────────┐
           │ Python local bus │◄──►│  Rust forwarding layer │
           └───────┬──────────┘    └────────┬───────────────┘
                   │                        │
                   │  (tap writes JSON      │  (Tauri emit)
                   │   lines to a           │
                   │   dedicated socket     │
                   │   or stdin pipe)       │
                   ▼                        ▼
           Rust local bus          Frontend local bus
```

- Python has its own local bus; Rust has one; the frontend has one.
- A **forwarding layer** in Rust subscribes to Python's bus (via stdout/socket), re-publishes on Rust's local bus, and `emit`s to the frontend. Symmetric for the other direction.
- This means a Python publish is visible to all three processes, with the cross-process hops being async.
- Subscribers in any process see all events regardless of origin (assuming no slow-handler drops).

Implementation detail owned by task 0003.

### Decision 12 — Error handling in handlers

A handler that raises/throws:
- Is logged at ERROR level with the event type, subscriber id, and stack trace.
- **Does not** interrupt dispatch to other handlers.
- **Does not** propagate to the publisher.

A handler is responsible for its own error handling. If it wants to communicate failure, it publishes an error event — it can't "return failure" to the publisher.

### Decision 13 — Tests required before task 0003 is Done

The contract isn't real until verified. Task 0003's acceptance criteria must include tests for:

- In-process FIFO ordering (publish A then B; handler sees A then B).
- Unsubscribe stops delivery.
- Oversize payload throws at publish.
- Slow handler drops on overflow (simulated).
- Handler exception doesn't break dispatch to peers.
- Cross-process round trip (Python publish → frontend sees; and reverse) within 100ms on localhost.

Add these to task 0003 as explicit acceptance checks.

## Alternatives considered

### A. Persistent event log with replay

Make the bus a durable log. Rejected for v0.2: adds implementation complexity, disk I/O cost, persistence format to version, GC pressure. Modules that need persistent state have their own SQLite. The bus stays a signaling primitive.

### B. Guaranteed ordering across processes

Would require sequence numbers + a central ordering broker. Rejected: cost-benefit doesn't pay off for v0.2 workloads. Timestamps + subscriber-side sort handles the rare cases that care.

### C. Wildcard subscriptions

Rejected per Decision 5. Can add in v0.3 if a real use case appears.

### D. Per-event-type rate limiting

Useful if a pathological module publishes 10k times/sec. Rejected for v0.2 — we don't have modules that do this. Ad-hoc rate limits at the publisher are fine for now.

### E. Typed bus per module (Forge bus, Current bus, etc.)

Would enforce module isolation at the bus layer. Rejected: cross-module event flow (Atlas observes Forge saves) is a first-class v0.2 need, and splitting the bus adds plumbing per-cross. Module isolation at the bus layer is illusory — every subscriber sees every event it subscribes to regardless of bus identity.

## Impact

- **Bus implementations:** task 0003 delivers three bus implementations (Python, Rust, frontend) + the forwarding layer — all constrained by these rules.
- **Contracts touched:** `src/contracts/events.ts` — every existing and future event must have `timestamp: number`. Audit existing event specs in the architecture docs during task 0003 and add any missing timestamps.
- **No migrations.** Bus is ephemeral.
- **Docs updated:** `planning/10-architecture/ipc-contracts.md` §3 gets a "see RFC-0005 for full semantics" pointer.
- **Rollback:** bus implementations can be rewritten freely as long as these external guarantees hold. Consumers are insulated by the guarantees, not the implementation.

## Open questions

- **OQ-5-1:** Should `MAX_PENDING_PER_SUBSCRIBER` be configurable per subscriber? **Decision:** not in v0.2. Single global value. Revisit when a real slow subscriber case emerges.
- **OQ-5-2:** If Rust forwarding crashes, is there a recovery? **Decision:** the forwarding layer is part of the sidecar lifecycle; if it dies, the sidecar dies, preflight-gate kicks in on restart. No standalone recovery path needed.
- **OQ-5-3:** Should events be accessible via Tauri IPC to outside-shell tools (e.g., a debug CLI)? **Decision:** not v0.2. If needed, expose via a deliberate debug-only Tauri command. The bus itself does not have an external API.

## Decision log

- 2026-04-15 (claude): initial draft and accepted. Binds task 0003.
