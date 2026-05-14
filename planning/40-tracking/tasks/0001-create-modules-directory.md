---
id: 0001
title: Create modules/ directory and workspace manifests
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0002, 0010, 0030, 0050]
blocked_by: []
related_rfc: null
pr: null
---

# 0001 — Create modules/ directory and workspace manifests

## Context

Every v0.2 module fold-in starts by dropping code under `modules/<name>/`. That directory doesn't exist yet and the project's top-level `package.json` and `pyproject.toml` don't know about workspace subpackages. Fix the plumbing before anyone tries to vendor a module.

## Scope

**In scope:**
- Create empty `modules/` directory at repo root with a README explaining the layout rule.
- Update root `package.json` to recognize `modules/*/frontend` as workspaces (npm workspaces or bun workspaces — match whatever's already used).
- Update or create root `pyproject.toml` (or whichever Python workspace mechanism the backend uses; check `backend/pyproject.toml`) to recognize `modules/*/backend` as subprojects.
- Add a top-level `.gitignore` entry excluding `modules/*/_vendor/` from linting/formatting tools that recurse (keep it in git though — vendored code under review must be trackable).

**Out of scope:**
- Creating any individual module directory (that's 0011, 0031, 0051).
- Writing MODULE.toml (that's 0004).

## Files to touch

- (NEW) `modules/README.md` — short explainer pointing at `planning/10-architecture/module-boundaries.md`.
- `package.json` — add to `workspaces` array.
- `backend/pyproject.toml` — add workspace declaration or whatever Python packaging uses.
- `.gitignore` — exclusion rules.

## Acceptance criteria

- [ ] `modules/README.md` exists and is under 40 lines.
- [ ] `ls modules/` returns only `README.md`.
- [ ] `bun install` (or equivalent) succeeds at repo root.
- [ ] `cd backend && pip install -e .` (or whatever command works today) still succeeds.
- [ ] `git status` is clean after the install commands.

## Implementation notes

- Check which package manager the repo uses: look for `bun.lockb` / `package-lock.json` / `pnpm-lock.yaml`. Match it.
- Do NOT set up any tree-sitter, tauri, or backend deps under `modules/` yet.
- Keep `modules/README.md` tiny — it points at the planning docs, doesn't duplicate them.

## Verification commands

```bash
ls modules/
cat modules/README.md | wc -l  # should be < 40
bun install
cd backend && pip install -e .
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-17 (claude): verified — `modules/README.md` exists, `package.json` workspaces set to `modules/*/frontend`. Status bumped `ready → done`.
