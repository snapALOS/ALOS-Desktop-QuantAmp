# ALOS — Vision

## What ALOS is

ALOS (**A**utonomous **L**ocal **O**perating **S**ystem) is a desktop-first, local-first agentic ecosystem. The "OS" in the name is literal: ALOS is not a chat app with tool-use — it is an **environment** where multiple specialized modules cooperate, orchestrated by agents, operating on the user's machine with the user's data.

## What changed between v0.1 and v0.2

**v0.1** was an agent swarm chat wrapped in a Tauri shell. Correct foundation, narrow surface.

**v0.2** folds in three production-shaped modules that together transform ALOS into an agentic IDE with workflow orchestration and live code intelligence:

- **ALOSForge** — a real IDE (Monaco, xterm, portable-pty, VS Code-style chrome) that agents operate alongside the user.
- **ALOSCurrent** — a DAG workflow orchestrator (triggers, schedules, human-in-the-loop, audit) that runs *above* the agent runtime, letting users define long-running automations that stitch modules together.
- **ALOSAtlas** — a SQLite-backed code intelligence graph (impact analysis, change scope, symbol context) exposed to agents via MCP.

## Design tenets (non-negotiable)

1. **Local-first.** No mandatory cloud. A user on a plane with their machine can do everything.
2. **Modular with hard boundaries.** Every module is independently reasonable, independently buildable, and — post-v1 — independently marketable. An agentic IDE must never scatter unrelated code across the tree: errors stay contained to one module.
3. **Agents are participants, not gods.** Agents have capabilities, gates, risk classes, and auditable routing. The user is always in the loop.
4. **Observability by default.** Every agent turn, every workflow step, every code-graph query writes to an audit log.
5. **The UI is a cooperation surface.** Humans and agents share the same editor, terminal, and workflow canvas. The user sees what the agent is doing in real time.

## v0.2 release story (one paragraph)

> ALOS Desktop v0.2 turns your machine into an agentic development environment. Open a file in **Forge**, ask an agent to refactor it — the agent consults **Atlas** to understand the blast radius before touching anything, then runs the change through a **Current** workflow that lints, tests, and requests your approval before committing. Every step is visible, every decision is auditable, everything runs locally.

## Long-term (v1.0 and beyond)

- **Cortex** lands: in-app model training/fine-tuning/swap.
- **Reflex** lands: scenario testing for agent behavior.
- Every module exposes a **standalone mode** (its own binary, its own installer) so each can earn attention outside of ALOS and bring users *back* into ALOS.
- ALOS becomes the umbrella brand; each module becomes a recognizable product.

## Non-goals for v0.2

- Multi-user collaboration (single-user desktop only).
- Cloud-hosted control plane.
- Mobile.
- Cortex, Reflex, and standalone-mode packaging (all deferred but architecturally reserved).
