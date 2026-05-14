---
id: 0003
title: Define event bus contract and publish/subscribe helpers
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: m
blocks: [0038, 0055]
blocked_by: [0001]
related_rfc: null
pr: null
---

# 0003 — Define event bus contract and publish/subscribe helpers

## Context

Modules must not import each other. All cross-module influence flows through typed events. v0.2 needs a working event bus before Current can trigger on `forge.file.saved` or Atlas can react to workspace open.

See [`planning/10-architecture/ipc-contracts.md`](../../10-architecture/ipc-contracts.md) §3 for the rules.

## Scope

**In scope:**
- `src/contracts/events.ts`: the discriminated-union `AlosEvent` type, seeded with every event named in the architecture docs (forge.*, atlas.*, current.*, agent.*). Events can be stubbed with minimal payloads — they don't have to be wired to real publishers yet.
- `src/shell/event-bus.ts`: in-process pub/sub for the frontend. Typed `publish(event)` and `subscribe(type, handler): unsubscribe` functions.
- Python counterpart `backend/src/alos_core/events.py`: mirror contract + in-process pub/sub. Same event names. Same payload shapes.
- A thin bridge: Tauri events carry events from Python → frontend and back (use `emit` / `listen`).

**Out of scope:**
- Any module actually publishing or subscribing (those are their own tasks).
- Persisting events (audit log — that's Current's concern).
- Cross-process fan-out (we're single-sidecar in v0.2).

## Files to touch

- (NEW) `src/contracts/events.ts`
- (NEW) `src/shell/event-bus.ts`
- (NEW) `src/shell/__tests__/event-bus.test.ts`
- (NEW) `backend/src/alos_core/events.py`
- (NEW) `backend/tests/unit/test_events.py`
- `src-tauri/src/lib.rs` — add the bridge: on python event, emit to frontend; on frontend publish, forward to python if anyone's listening

## Acceptance criteria

- [ ] Publishing `{ type: 'forge.file.saved', path: '/x', timestamp: 123 }` from the frontend and subscribing to the same type delivers the payload.
- [ ] Same round-trip works in Python.
- [ ] Frontend publish is received by a Python subscriber, and vice versa, within 100ms on localhost.
- [ ] Unsubscribe actually stops delivery.
- [ ] Unit tests pass in both languages.
- [ ] TypeScript strict compilation passes — the `AlosEvent` union is fully typed, no `any`.

## Implementation notes

- Keep the bus minimal: subscribe by exact event type string. Wildcard or pattern matching is v0.3+.
- Use Tauri's built-in event system (`emit` + `listen`) for the cross-process bridge; don't invent a new IPC channel.
- For Python ↔ frontend bridge: the Rust core subscribes to all Python events over a localhost socket or stdin/stdout and re-emits as Tauri events. Use whatever IPC shape is already in `backend/` today.
- Event payloads are JSON-serializable only. No circular refs. No functions.

## Verification commands

```bash
bun run test -- event-bus
cd backend && pytest tests/unit/test_events.py
bun run build
cd src-tauri && cargo check
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-17 (claude): verified. `src/contracts/events.ts` + `src/shell/event-bus.ts` exist. Python side lives at `backend/src/core/event_bus/events.py` (path diverges from spec — final location is fine, 11/11 pytest passing via `test_event_bus.py`). Frontend round-trip test covered under `src/shell/__tests__/event-bus.test.ts`. Bridge centralised in `src/shell/tauri-bridge.ts` (idempotent `listen('alos-event')` + `forwardToBackend()` via `forward_event_to_backend` Rust command). Status `ready → done`.
