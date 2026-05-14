---
id: 0010
title: Forge — vendor source and produce INVENTORY.md
area: forge
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0011]
blocked_by: [0001]
related_rfc: null
pr: null
---

# 0010 — Forge — vendor source and produce INVENTORY.md

## Context

First step of the Forge fold-in (Phase 1). Before moving code around we take stock: every file, its size, language, and a decision — keep / drop / rewrite — plus the contract it belongs to post-fold.

See [`planning/20-modules/forge/integration-plan.md`](../../20-modules/forge/integration-plan.md) Phase 1.

## Scope

**In scope:**
- Copy `Upgrades From Rex/rexcode proprietary-ide/` (or `/Volumes/DDrive/Rex'S Upgrades/rexcode proprietary-ide/` if not yet moved) → `modules/forge/_vendor/`.
- Produce `modules/forge/_vendor/INVENTORY.md`: a table with columns `path | size | language | decision | target path | notes`.
- Decisions are: `keep` (move to target with minimal changes), `drop` (HubAdapter code, RexBot-branded demo data), `rewrite` (needs substantial change during fold-in).
- Target paths are under `modules/forge/frontend/` or `modules/forge/backend/` or `src-tauri/src/forge/`.

**Out of scope:**
- Moving any file out of `_vendor/`. This task is read-only stocktaking.
- Making any decisions that need an RFC. Flag those as "DECISION TBD — write RFC" in the notes column.

## Files to touch

- (NEW) `modules/forge/_vendor/**` — the vendored tree
- (NEW) `modules/forge/_vendor/INVENTORY.md`

## Acceptance criteria

- [ ] `modules/forge/_vendor/INVENTORY.md` exists.
- [ ] Every top-level file in the vendored tree appears in the inventory (directories may be summarized as "N files, same decision" if truly uniform).
- [ ] Every row has a decision filled in — no TBDs except in notes.
- [ ] Total count in inventory == `find modules/forge/_vendor -type f | wc -l` ± acceptable grouping.
- [ ] HubAdapter files are all decisioned `drop`.
- [ ] Monaco/xterm integration files are decisioned `keep`.
- [ ] At least one "rewrite" exists (expected: the app entry point, which needs shell-mount instead of standalone-bootstrap).

## Implementation notes

- Keep `INVENTORY.md` as a markdown table. Grep-friendly is more important than pretty.
- If a file's decision depends on a decision not yet made, write "DECISION TBD" in the notes and describe what it depends on. That becomes a prerequisite task.
- Binary/asset files (icons, images) get their own rows with decision — we swap assets during rebrand.

## Verification commands

```bash
ls modules/forge/_vendor/ | head
wc -l modules/forge/_vendor/INVENTORY.md
find modules/forge/_vendor -type f | wc -l
grep -c 'TBD' modules/forge/_vendor/INVENTORY.md  # should be manageable, not huge
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-16 (opus): vendor tree copied to `modules/forge/_vendor/`; INVENTORY.md written to the 6-column schema.
- 2026-04-17 (claude): verified schema and completeness. Status `ready → done`.
