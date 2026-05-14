# ALOSForge — Rebrand Checklist

**Goal:** zero occurrences of RexCode-era names outside `_vendor/` (temporary) and `planning/` (documentation).

## String-replacement table

| Find (case-insensitive) | Replace with |
|---|---|
| `RexCode` | `ALOSForge` |
| `rexcode` (identifier) | `alos_forge` or `alosForge` depending on context |
| `rex-code` | `alos-forge` |
| `Rex Code` | `ALOS Forge` |
| `RexBot` | `ALOS` (or remove entirely if about the agent fleet — context-dependent) |
| `RexHub` | (delete related features; HubAdapter dropped for v0.2) |
| `rex` as bare identifier | inspect; usually `alos` or drop |

## File renames

| Old | New |
|---|---|
| `src/adapters/TauriAdapter.ts` | keep path; remove adapter abstraction, use direct `@tauri-apps/api` |
| `src/adapters/HubAdapter.ts` | **delete** |
| `src/hooks/useIsAgentObserving.ts` | `modules/forge/frontend/src/hooks/useAgentObservation.ts` |
| `RexCodeApp.tsx` | `ForgeApp.tsx` |
| any file starting with `rex` | strip prefix or rename to `alos-` prefix where a prefix is appropriate |

## Config & identifier changes

- **Tauri product name:** stays `ALOS` (set in `tauri.conf.json`).
- **Bundle identifier:** stays `com.alos.desktop`.
- **Python package:** `rexcode` → `alos_forge`.
- **npm package (internal):** `@rexcode/ide` → `@alos/forge`.
- **Cargo crate (internal):** `rexcode` → `alos_forge` (if there's a dedicated crate; otherwise just a module path).
- **Theme ID:** `rex-dark` → `alos-dark`.
- **CSS root class:** `.rex-root` → `.alos-root` or `.forge-root` (scope as tight as possible).

## User-facing strings

- **Window title contribution:** stays `ALOS` (Forge is a module, not the app).
- **Empty-state editor text:** "Welcome to ALOS Forge" (not "RexCode").
- **Command palette header:** `ALOS Forge` under the module dropdown.
- **Logo / icon:** use ALOS icon, not RexCode logo. Source asset at `src-tauri/icons/`.

## Log lines

- Every `log::info!` / `logger.info` with `rexcode` in it must become `forge` or `alos_forge`.
- Log level prefixes: `[rexcode]` → `[forge]`.

## Verification grep (must return zero)

```bash
# Run from ALOS-Desktop root
grep -rni --include='*.{ts,tsx,py,rs,md,json,toml,yaml,yml,css,scss,html}' \
  -E '\b(rexcode|rex-code|rex code|rexbot|rexhub)\b' \
  modules/forge/ src/ src-tauri/ backend/
```

Acceptance: zero matches. One exception: the `_vendor/` directory during Phase 1–5 (deleted in Phase 6).

## Notes for agents

- When renaming, **always update imports in the same commit**. Never leave a broken tree.
- Use `rg` (ripgrep) or the Grep tool — do not use `find`.
- If a name appears in a binary asset (icon, image), flag it in the task file. Assets are swapped by hand.
