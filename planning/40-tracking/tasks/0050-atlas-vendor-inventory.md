---
id: 0050
title: Atlas — vendor source and produce INVENTORY.md
area: atlas
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0051]
blocked_by: [0001]
related_rfc: null
pr: null
---

# 0050 — Atlas — vendor source and produce INVENTORY.md

## Context

Phase 1 of the Atlas fold-in. Stocktake before moving anything.

See [`planning/20-modules/atlas/integration-plan.md`](../../20-modules/atlas/integration-plan.md) Phase 1.

## Scope

**In scope:**
- Copy `Upgrades From Rex/rexnexus/` (or equivalent source on DDrive) → `modules/atlas/_vendor/`.
- Produce `modules/atlas/_vendor/INVENTORY.md` with columns `path | size | language | decision | target path | notes`.
- Specific attention:
  - Tree-sitter parser bindings: note per-language which grammars are vendored as code vs installed at runtime. The bundling strategy depends on this.
  - The MCP server file: decision `keep` with target `modules/atlas/backend/src/alos_atlas/mcp_server.py`.
  - Any hardcoded path assuming `~/.rexnexus/`: decision `rewrite` to `~/.alos/atlas/`.

**Out of scope:**
- Any code movement.

## Files to touch

- (NEW) `modules/atlas/_vendor/**`
- (NEW) `modules/atlas/_vendor/INVENTORY.md`

## Acceptance criteria

- [ ] Inventory exists and is comprehensive.
- [ ] Tree-sitter bundling strategy is identified per-language and captured in the notes column.
- [ ] MCP server file is decisioned `keep`.
- [ ] All `~/.rexnexus/` references are decisioned `rewrite`.
- [ ] Current tool names (`impact`, `change_scope`, etc.) are captured with target names (`atlas_impact_symbol`, etc.) in the notes.

## Implementation notes

- Atlas source is expected to be the smallest of the three — budget ~1–2 hours.
- If tree-sitter grammars are vendored as compiled shared libs, note OS + arch per lib so the packaging task can produce a plan.

## Verification commands

```bash
ls modules/atlas/_vendor/
wc -l modules/atlas/_vendor/INVENTORY.md
grep -c 'tree-sitter\|tree_sitter' modules/atlas/_vendor/INVENTORY.md
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-16 (opus): vendor tree copied; INVENTORY.md written.
- 2026-04-17 (claude): verified schema and completeness. Status `ready → done`.
