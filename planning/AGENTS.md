# AGENTS.md — Onboarding for AI contributors

**If you are an AI coding agent starting a session in this repository, read this file before doing anything else.** This is ~5 minutes of reading and it prevents hours of rework.

## What this codebase is

ALOS Desktop is a Tauri 2 + React + TypeScript desktop app with a Python (LangGraph) sidecar and a Rust core. It is in active development toward **v0.2**, which folds in three formerly-separate modules — **ALOSForge** (IDE shell), **ALOSCurrent** (workflow orchestrator), **ALOSAtlas** (code intelligence graph) — rebranded from RexCode / RexFlow / RexNexus.

## The one-paragraph context

The repo ships with v0.1 working (agent swarm + tray + preflight + backend spawn). v0.2 work is planned but not started. All design decisions live under `planning/`. Task scope lives under `planning/40-tracking/tasks/`. Your job, whatever it is, traces back to a task file.

---

## Before you touch any code

Read these in order. Do not skip. Do not skim past the names.

1. [`planning/README.md`](planning/README.md) — map of the planning bundle.
2. [`planning/00-overview/naming.md`](planning/00-overview/naming.md) — **locked module names.** Memorize. Dead names (RexCode/RexFlow/RexNexus/RexBot/RexHub) in your output will be reverted.
3. [`planning/00-overview/vision.md`](planning/00-overview/vision.md) — what ALOS is becoming.
4. [`planning/10-architecture/system-architecture.md`](planning/10-architecture/system-architecture.md) — topology.
5. [`planning/10-architecture/module-boundaries.md`](planning/10-architecture/module-boundaries.md) — the isolation rules.
6. [`CONVENTIONS.md`](CONVENTIONS.md) — how to write code that matches what's already here.
7. [`planning/50-glossary/glossary.md`](planning/50-glossary/glossary.md) — if a term is unfamiliar, look it up before using it.

After those, consult the specific docs your task references.

---

## How to pick up a task

### 1. Check the board

Open [`planning/40-tracking/board.md`](planning/40-tracking/board.md). Look at the **Ready** column.

If the user gave you a specific task id (e.g., "work on 0002"), skip to step 2. Otherwise, pick one:

- Prefer tasks with no open blockers and low `effort` for your first pass.
- Never pick a task already in `In Progress`.

### 2. Read the task file end to end

`planning/40-tracking/tasks/NNNN-slug.md`. You are looking for:

- **Context** — the "why."
- **Scope / In scope / Out of scope** — the boundary. Do not cross it.
- **Files to touch** — the initial file map.
- **Acceptance criteria** — mechanically verifiable. These are what "done" means. If you complete the work but a criterion isn't met, you are not done.
- **Verification commands** — run these before declaring completion.

If the scope is unclear, stop. Update the task file with questions, commit the doc change, and ping the user. Do not guess.

### 3. Claim the task

Atomically:
- Edit the task file frontmatter: `status: in_progress`, `assigned_to: <your handle>`, `updated: YYYY-MM-DD`.
- Move the row in `board.md` from **Ready** to **In Progress**.
- Append a status update line at the bottom of the task file: `- YYYY-MM-DD (<handle>): claimed.`
- Commit: `[NNNN] claim task` before any code.

If you lose the race to another agent (commit fails / conflict), step back and pick a different task.

### 4. Work

- Stay inside the task's **In scope** list.
- If you find related work that's needed, create a **new** task file; do not silently expand.
- Follow `CONVENTIONS.md` rigorously. Match existing code style — inspect 2 similar files before writing a new one.
- Write tests in the same PR (`CONVENTIONS.md` §4 for Python test style, §3 for TS).
- When you modify a contract, update the matching doc under `planning/` in the same commit.

### 5. Verify

Run **every** verification command in the task file. Then run the CONVENTIONS §12 three questions:

1. `grep` shows zero dead-name matches in the changes.
2. Linters/formatters pass.
3. Every acceptance criterion mechanically checks off.

If any fail, keep working. Do not mark done.

### 6. Finish

- Edit task frontmatter: `status: review` (or `done` if no PR is in flight — e.g., solo commit to main).
- Add `pr: <url>` if applicable.
- Move the row on `board.md`.
- Append a status update: `- YYYY-MM-DD (<handle>): completed. <link to PR or commit>`.
- Commit the doc change in the same commit as the code (or immediately before/after).

---

## What you must not do

- **Do not** rename modules, files, or identifiers to the dead names, even if you see the dead name referenced somewhere as context. If you spot a drift bug, file a task, do not "helpfully" propagate the drift.
- **Do not** invent new top-level directories, new IPC channels, or new cross-module event types without an RFC in `planning/30-rfcs/`.
- **Do not** change contract files in non-additive ways without an RFC.
- **Do not** add dependencies (npm / Python / Cargo) without an RFC. Use what's already there.
- **Do not** write into `Upgrades From Rex/` — it's a read-only reference snapshot.
- **Do not** delete or rewrite `planning/` docs. Update in place; mark superseded if needed.
- **Do not** run destructive git commands (`reset --hard`, `push --force`, `branch -D`, `clean -f`) without an explicit instruction in the task or from the user.
- **Do not** skip pre-commit hooks (`--no-verify`) without an explicit instruction.

---

## When you're stuck

1. Re-read the task file. 80% of "stuck" is a scope question the task file already answered.
2. Check the module's `overview.md` and `integration-plan.md` under `planning/20-modules/<area>/`.
3. Grep for similar patterns in existing code.
4. If still stuck: append a `blocked_by` note in the task's frontmatter (can be a prose explanation), move to **Blocked** on the board, commit, and stop. The user or another agent resolves the block.

Don't loop trying things. Don't fake progress. "Blocked" is a valid outcome and honest blocking is more valuable than cheerful wrongness.

---

## The fast-path version (for agents picking up repeat work)

```
1.  git pull
2.  cat planning/40-tracking/board.md
3.  open planning/40-tracking/tasks/NNNN-*.md
4.  claim (edit frontmatter + board, commit)
5.  work inside scope; match CONVENTIONS.md
6.  run verification commands; re-read acceptance criteria
7.  grep for dead names (CONVENTIONS §8) → zero
8.  mark done (edit frontmatter + board, commit)
```

---

## Communicating with the user

- Keep session responses compact. The user reads a lot of them.
- When you need a decision, ask one clean question at a time, not a batched list of hedges.
- When you report completion, link the specific task id and the exact commit / PR.
- If you wrote a doc, link it.
- Do not editorialize. Say what you did and what's next.

---

## If this document conflicts with a task file

Task file wins for scope. This document wins for process. `CONVENTIONS.md` wins for style.

If two win-for rules collide: stop and ask. That's a planning bug, not an execution choice.
