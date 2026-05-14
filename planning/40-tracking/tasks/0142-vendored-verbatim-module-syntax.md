---
id: 0142
title: Fix verbatimModuleSyntax + implicit-any in vendored module code
area: core
status: done
assigned_to: claude
created: 2026-04-17
updated: 2026-04-17
effort: m
blocks: [0143]
blocked_by: [0141]
related_rfc: null
pr: null
---

# 0142 — Fix verbatimModuleSyntax + implicit-any in vendored module code

## Context

Root `tsconfig.app.json` has `"verbatimModuleSyntax": true` and
`"noUnusedLocals": true`, which the vendored Forge and Current frontends
violate in ~25 places (type-as-value imports) plus ~8 places with implicit
`any` callback parameters. After 0141 resolves the missing-package errors,
this pile becomes the only remaining class of TS errors from
`npx tsc -b --noEmit`.

Fixing them is mechanical:

- `import { Foo }` → `import type { Foo }` where `Foo` is only used in types.
- `onChange={(e) => …}` → `onChange={(e: ChangeEvent<HTMLInputElement>) => …}`
  (or `: unknown` with a type narrow inside).
- Remove unused imports flagged by `noUnusedLocals`.
- `ChamberView.tsx` line 2 — replace `@/services/api` with the correct ALOS
  `@/api` alias (or delete the stale import if nothing uses it).

## Scope

**In scope:**
- Bring every file under `modules/**/frontend/src/**/*.ts{,x}` clean under
  the root `tsconfig.app.json`.
- Fix the `@/services/api` → `@/api` alias mismatch in
  `modules/chamber/frontend/src/ChamberView.tsx`.

**Out of scope:**
- Rewriting any vendored component logic. This is a pure type-annotation
  pass.
- Relocating files.

## Files to touch

Enumerate per `tsc` output. Biggest offenders as of 2026-04-17:

- `modules/current/frontend/src/App.tsx` (~11 sites)
- `modules/current/frontend/src/components/workflow-canvas/WorkflowCanvas.tsx` (~8 sites)
- `modules/current/frontend/src/utils/compiler.ts` (~5 sites)
- `modules/forge/frontend/src/store/useIDEStore.ts` (1 site)
- `modules/forge/frontend/src/components/**/*.tsx` (implicit-any params)
- `modules/chamber/frontend/src/ChamberView.tsx` (alias + unused import)

## Acceptance criteria

- [x] `npx tsc -b --noEmit` exits 0 with no output.
- [x] `npm run build` succeeds.
- [x] No vendored file was deleted.
- [x] No vendored file had logic changed beyond imports and callback type
      annotations.

## Implementation notes

- When in doubt between `import type {X}` and keeping `X` as a value,
  check: is `X` ever used as a constructor, a function call, or a JSX
  element? If not, make it a type import.
- Resist the temptation to loosen the root tsconfig. These are real
  type-safety guarantees; vendored code gets updated to match the project
  standard, not the other way around.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
# Count remaining errors in vendored code (should be 0):
npx tsc -b --noEmit 2>&1 | grep -c '^modules/'
```

## Status updates

- 2026-04-17 (claude): created. Unblocked once 0141 lands the missing deps.
- 2026-04-17 (claude): done. Mechanical pass. Files touched (imports
  only, no logic edits):
  - `modules/current/frontend/src/App.tsx` — split React import
    (`ChangeEvent` → `type`), converted 10-symbol `./types/workflow`
    import to `import type`.
  - `modules/current/frontend/src/components/workflow-canvas/WorkflowCanvas.tsx`
    — split React import (`PointerEvent` → `type`), converted
    `../../types/workflow` import to `import type`, added missing
    `Agent` to the type-import list (fixes TS2304 x2 on lines 31, 319).
  - `modules/current/frontend/src/utils/compiler.ts` — 5-symbol
    `import` → `import type`.
  - `modules/forge/frontend/src/components/explorer/FileTree.tsx` —
    `FileInfo` → `import type`.
  - `modules/forge/frontend/src/components/search/SearchPanel.tsx` —
    `SearchResult` → `import type`.
  - `modules/forge/frontend/src/components/settings/SettingsPanel.tsx`
    — `AppConfig` → `import type`.
  - `modules/forge/frontend/src/store/useIDEStore.ts` —
    `EnvironmentAdapter` → `import type`.
  - `modules/forge/frontend/src/components/layout/BottomPanel.tsx` —
    removed unused `IconButton` import.
  - `modules/chamber/frontend/src/ChamberView.tsx` — deleted stale
    `import { api } from '@/services/api'` (unused, wrong alias).
  - `modules/forge/frontend/tsconfig.json` — removed stale
    `references: [{ path: './tsconfig.node.json' }]` (file did not
    exist; broke `npm run build` in Vite's tsconfig scan).
  Verification:
  - `npx tsc -b --noEmit` → exit 0, zero errors.
  - `npx tsc -b --noEmit 2>&1 | grep -c '^modules/'` → 0.
  - `npm run build` → success, `dist/` produced (~900 KB bundle).
  The implicit-any TS7006 errors listed in the scope disappeared on
  their own once the React 19 types were properly resolved (they were
  cascading from the earlier ReactNode type mismatch, not genuine
  missing annotations).
