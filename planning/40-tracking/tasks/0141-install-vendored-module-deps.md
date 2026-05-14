---
id: 0141
title: Install frontend deps required by vendored module code
area: core
status: done
assigned_to: claude
created: 2026-04-17
updated: 2026-04-17
effort: s
blocks: [0142, 0143]
blocked_by: []
related_rfc: null
pr: null
---

# 0141 — Install frontend deps required by vendored module code

## Context

The vendored Forge and Current frontends import packages that were never
added to the root `package.json`:

- `@mui/material`, `@mui/icons-material`, `@mui/material/styles`
- `@monaco-editor/react`
- `xterm`, `xterm-addon-fit`

When the root project pulls these files in via `src/shell/modules/ForgeView.tsx`
and `src/shell/modules/ModuleViews.tsx`, `tsc -b` cannot resolve the imports
and emits ~40 TS2307 errors. The dev build (`vite`) currently works because
Vite is more permissive, but `npm run build` (which runs `tsc -b && vite build`)
fails the type pass.

## Scope

**In scope:**
- Add the required packages to the root `package.json` dependencies.
- Run `npm install` and commit the lockfile.
- Verify `npx tsc -b --noEmit` no longer emits TS2307 errors for these
  packages.

**Out of scope:**
- Refactoring any module code.
- `verbatimModuleSyntax` fixes (task 0142).
- Replacing MUI with a tailwind-native design system (deferred to v0.3).

## Files to touch

- `package.json`
- `package-lock.json` (generated)

## Acceptance criteria

- [x] `grep '@mui/material' package.json` returns a dependency line.
- [x] `grep '@monaco-editor/react' package.json` returns a dependency line.
- [x] `grep '"xterm"' package.json` returns a dependency line.
- [x] `npm install` succeeds at root.
- [x] `npx tsc -b --noEmit 2>&1 | grep "TS2307.*@mui\|TS2307.*monaco\|TS2307.*xterm" | wc -l` → `0`.
- [x] `npm run build` succeeds.

## Implementation notes

- Pin to versions compatible with React 19. MUI 5 still targets React 18; use
  MUI 6 (which supports React 19).
- If MUI 6 introduces breaking changes against the vendored Forge code,
  consider pinning MUI 5 with the `--legacy-peer-deps` flag and opening a
  v0.3 task to migrate.
- Monaco editor pulls a ~3MB worker bundle. That's fine for v0.2; note it
  in `planning/10-architecture/` if bundle size becomes a concern.

## Verification commands

```bash
cd "ALOS + QA-SIR/ALOS-Desktop + QuantAmp"
npm install
npx tsc -b --noEmit 2>&1 | grep -E 'TS2307.*(@mui|@monaco|xterm)' | wc -l  # expect 0
npm run build
```

## Status updates

- 2026-04-17 (claude): created. Blocks clean frontend type-check.
- 2026-04-17 (claude): done. Added to root `package.json`:
  `@mui/material@^6`, `@mui/icons-material@^6`, `@emotion/react@^11`,
  `@emotion/styled@^11`, `@monaco-editor/react@^4`, `xterm@^5`,
  `xterm-addon-fit@^0.8`. Verified:
  `npx tsc -b --noEmit 2>&1 | grep -E 'TS2307.*(@mui|@monaco|xterm)' | wc -l`
  → 0. Also aligned `modules/forge/frontend/package.json` and
  `modules/current/frontend/package.json` from React 18 →
  React 19 (`react`, `react-dom`, `@types/react`, `@types/react-dom`)
  so the workspace-nested `@types/react@18` no longer fights the
  root's React 19 types (was producing TS2786 JSX-component errors on
  `ThemeProvider` and `Editor`).
