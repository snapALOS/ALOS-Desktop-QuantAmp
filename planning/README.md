# ALOS-Desktop Planning Bundle

**Purpose:** single source of truth for the v0.2 release and beyond. Every contributor — human or AI agent — reads from and writes to this directory. If it isn't here, it isn't decided.

**Status:** v0.2 in active planning. v0.1 shipped (agent swarm, tray, preflight, backend sidecar).

**If you are an AI agent**, read [`../AGENTS.md`](../AGENTS.md) before this file. It is your onboarding path and takes ~5 minutes.

**For code style**, read [`../CONVENTIONS.md`](../CONVENTIONS.md) — the locked style rules for TypeScript, Python, and Rust in this repo.

---

## Nav

### 00 · Overview
- [vision.md](00-overview/vision.md) — what ALOS is becoming (agentic IDE / OS)
- [naming.md](00-overview/naming.md) — **locked module names. Do not drift.**
- [roadmap.md](00-overview/roadmap.md) — v0.1 → v0.2 → v1.0

### 10 · Architecture
- [system-architecture.md](10-architecture/system-architecture.md) — top-level diagram
- [module-boundaries.md](10-architecture/module-boundaries.md) — hard-isolation rules
- [module-registry.md](10-architecture/module-registry.md) — left-nav contract
- [agent-runtime.md](10-architecture/agent-runtime.md) — LangGraph (turn engine) vs ALOSCurrent (workflow)
- [ipc-contracts.md](10-architecture/ipc-contracts.md) — how modules talk
- [lsp-integration.md](10-architecture/lsp-integration.md) — LSP architecture for v0.2

### 20 · Modules
- **v0.2 scope:**
  - [forge/](20-modules/forge/) — ALOSForge (IDE shell, from RexCode)
  - [current/](20-modules/current/) — ALOSCurrent (workflow orchestrator, from RexFlow)
  - [atlas/](20-modules/atlas/) — ALOSAtlas (code intelligence graph, from RexNexus)
- **Future:**
  - [_future/cortex.md](20-modules/_future/cortex.md) — ALOSCortex (AI Model Lab)
  - [_future/reflex.md](20-modules/_future/reflex.md) — ALOSReflex (Scenario Toolkit)
  - [_future/sandbox.md](20-modules/_future/sandbox.md) — Sandbox (not a module; baked-in)

### 30 · RFCs
- [README.md](30-rfcs/README.md) — RFC process
- [_template.md](30-rfcs/_template.md)
- Numbered RFCs appear here as architecture decisions need written-down rationale.

### 40 · Tracking
- [README.md](40-tracking/README.md) — how to use the task system
- [board.md](40-tracking/board.md) — kanban (Backlog / Ready / In Progress / Review / Done)
- [tasks/_template.md](40-tracking/tasks/_template.md)
- [tasks/](40-tracking/tasks/) — every task, one file, YAML frontmatter

### 50 · Glossary
- [glossary.md](50-glossary/glossary.md) — every term, one definition

---

## Rules for all contributors (human and AI)

1. **Use the locked names.** RexCode, RexFlow, RexNexus are dead names. See [naming.md](00-overview/naming.md).
2. **One task = one file in `40-tracking/tasks/`.** Never work off verbal/chat scope.
3. **Every task's acceptance criteria must be mechanically verifiable** (file exists / test passes / grep matches). No "looks good."
4. **If you change an architectural decision, write an RFC first.** Don't silently diverge.
5. **Never cross module boundaries without an explicit contract.** See [module-boundaries.md](10-architecture/module-boundaries.md).
6. **Update task status in the task file and on `board.md` in the same commit.**
7. **If a term isn't in the glossary, add it before using it in code.**

---

## Quick start for a new agent

1. Read `00-overview/vision.md` (5 min).
2. Read `00-overview/naming.md` (1 min — memorize it).
3. Read `10-architecture/system-architecture.md` (5 min).
4. Check `40-tracking/board.md` for a task in **Ready**.
5. Read that task file end to end. Do not start work until acceptance criteria are understood.
6. Move the task to **In Progress** (edit `board.md` + task file frontmatter).
7. Work. Stay inside the task's scope. If you find adjacent work, file a new task.
8. When done: move to **Review**, open PR, link from the task file.
