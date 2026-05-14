# Sandbox — NOT a module

**The user's direction:** "the sandbox will be integrated in fully and won't need a spot."

Sandbox is **not** a module. It has no activity-bar entry, no `modules/sandbox/` directory, no independent lifecycle. It is a cross-cutting runtime capability that any module can consume to run untrusted or potentially-damaging code safely.

## Where it lives

- Rust primitives: `src-tauri/src/sandbox/` — process isolation, resource limits, filesystem jailing.
- Python helpers: `backend/src/sandbox/` — subprocess wrappers, stdin/stdout plumbing, timeout enforcement.

## Who uses it

- **Forge** — every `forge_run_command` MCP call (agent-initiated) runs through sandbox.
- **Current** — `shell` step type runs through sandbox.
- **Atlas** — doesn't need it (read-only against user filesystem).
- **Cortex / Reflex (future)** — will use sandbox for training-script execution and scenario driver isolation.

## Sandbox capability levels (rough sketch)

- **L0 — none:** run in the ALOS process context. Only trusted code.
- **L1 — process isolation:** separate subprocess, timeout, stdout/stderr captured. Default for agent-initiated shell.
- **L2 — filesystem jail:** L1 + bind mount / chroot / macOS sandbox-exec profile restricting writes to a workspace-scoped tmpdir.
- **L3 — network isolation:** L2 + deny outbound network except an allowlist. Future.

## v0.2 scope

- L0 and L1 implemented.
- L2 drafted behind a feature flag; default off.
- L3 deferred to v0.3+.

## Why it's here, not under modules

Sandbox doesn't have a UI. Sandbox doesn't have a public MCP surface. Sandbox doesn't have a user-visible concept. It is plumbing, not a destination. Modules consume it via a Rust crate + Python helpers; users never "open" sandbox.

## Source material

Check `Upgrades From Rex/sandbox/` for prior art. Most likely harvestable as functions/utilities, not as a module-sized drop-in.
