---
id: 0120
title: Write CONVENTIONS.md for agent contributors
area: docs
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-15
effort: s
blocks: []
blocked_by: []
related_rfc: null
pr: null
---

# 0120 — Write CONVENTIONS.md for agent contributors

## Context

Multiple agents (Claude, Gemini 3 Flash, Codex) will work against this codebase. Without a written-down conventions doc, each agent makes slightly different choices — import order, comment style, commit message shape, error handling — and the diff gets unreadable fast.

Codify the minimum conventions so any agent reading this file produces code indistinguishable from what any other agent produced.

## Scope

**In scope:**
- Create `CONVENTIONS.md` at repo root (or under `planning/` — decide based on visibility; probably `CONVENTIONS.md` at root for CI/agent discovery).
- Cover:
  - **Commit messages:** imperative mood, short subject (<72), blank line, optional body explaining why.
  - **Branch naming:** `task/NNNN-slug`.
  - **TypeScript:** `strict: true` must stay true; no `any` without an `eslint-disable` comment explaining why; prefer `type` over `interface` for pure data (keep existing codebase's convention if different — inspect first).
  - **Python:** type hints everywhere for new code; `ruff` + `black` must pass; docstrings in existing style.
  - **Rust:** `cargo fmt` + `cargo clippy -- -D warnings` must pass.
  - **Error handling:** no bare `except:` in Python; no `.unwrap()` in Rust production code (tests OK); no swallowed promises in TS.
  - **Logging:** use the existing logger (log crate in Rust, `log` in Python, `console` in TS). No `println!` or bare `print` in production code.
  - **Imports:** follow what each language's formatter produces. Don't re-order by hand.
  - **Testing:** any new contract gets a smoke test in the same PR.
  - **Docs:** when a task changes a contract, the `.md` file under `planning/` must update in the same commit. Acceptance criteria for that task must include "doc updated."
  - **No emoji in committed code** unless the existing file already uses them.
  - **Agent handles:** when logging agent activity (e.g., status updates in task files), use handles: `claude`, `gemini-3-flash`, `codex`, or `human:<name>`.

**Out of scope:**
- Full style guide — inspect existing code and match it. Only codify things where multiple agents would reasonably diverge.
- Linting config changes (keep existing configs).

## Files to touch

- (NEW) `CONVENTIONS.md` at repo root.
- `planning/README.md` — add a link to CONVENTIONS from the "Rules for all contributors" section.

## Acceptance criteria

- [ ] `CONVENTIONS.md` exists at repo root.
- [ ] Under 300 lines (concise; agents read it every session).
- [ ] Each section above is addressed.
- [ ] `planning/README.md` links to it.
- [ ] Running the project's formatters (`bun run lint`, `cd backend && ruff check .`, `cargo fmt --check`) shows no regressions against the baseline.

## Implementation notes

- Read existing code before writing conventions. Don't invent conventions that fight the current codebase.
- If a convention conflicts with existing code, file a cleanup task instead of retconning.
- Keep examples short. Two lines of code per example max.

## Verification commands

```bash
test -f CONVENTIONS.md
wc -l CONVENTIONS.md               # < 300
grep -l 'CONVENTIONS' planning/README.md
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-15 (claude): completed. Wrote `CONVENTIONS.md` (12 sections, ~300 lines) matching existing code style inspected across `src/App.tsx`, `src/api/client.ts`, `backend/src/agents/capabilities.py`, `src-tauri/src/backend.rs`, `backend/tests/unit/test_routing.py`. Also wrote `AGENTS.md` at repo root as a separate onboarding doc for AI contributors (task flow, do-not list, fast-path). Corrected MUI→Tailwind slip in task 0002.
