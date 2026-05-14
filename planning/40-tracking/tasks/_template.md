---
id: NNNN
title: Short imperative title
area: core | forge | current | atlas | lsp | agents | rebrand | docs
status: backlog
assigned_to: null
created: YYYY-MM-DD
updated: YYYY-MM-DD
effort: xs | s | m | l
blocks: []
blocked_by: []
related_rfc: null
pr: null
---

# NNNN — Title

## Context

Why this task exists. One paragraph. What's the bigger thing it unblocks?

## Scope

What this task does. Be explicit. "Add X, wire Y to Z." Also list non-goals — things someone might assume are part of this but aren't.

**In scope:**
- …

**Out of scope:**
- …

## Files to touch

Enumerate as much as you can in advance.

- `path/to/file.ts` — what changes
- `path/to/other.py` — what changes
- (NEW) `path/to/newfile.rs` — what it does

## Acceptance criteria

**All must be mechanically verifiable.**

- [ ] `grep -rn ... | wc -l` returns `0`.
- [ ] `bun run test:unit` passes.
- [ ] File `X` exists and imports `Y`.
- [ ] UI route `/foo` renders the `Bar` component when visited.
- [ ] Event `baz.qux.fired` is published when Z happens (observable via log).

## Implementation notes

Guidance, not prescription. Things a smart agent should know — tricky edge cases, prior-art references, paths to read first.

## Verification commands

Exact commands a reviewer runs after the PR.

```bash
bun run test:unit -- --grep 'module'
cd src-tauri && cargo check
grep -rn 'forbidden_string' modules/ | wc -l   # expect 0
```

## Status updates

Append-only log of meaningful moments. Date + agent handle + what.

- YYYY-MM-DD (agent): created.
