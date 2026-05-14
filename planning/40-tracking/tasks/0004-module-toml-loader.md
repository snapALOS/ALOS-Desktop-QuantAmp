---
id: 0004
title: Add MODULE.toml loader and nav-entry generator
area: core
status: done
assigned_to: claude
created: 2026-04-15
updated: 2026-04-17
effort: s
blocks: [0002]
blocked_by: [0001]
related_rfc: 0001
pr: null
---

# 0004 — Add MODULE.toml loader and nav-entry generator

## Context

The module registry (task 0002) discovers modules by scanning `modules/*/MODULE.toml`. That loader doesn't exist yet.

See [`planning/10-architecture/module-boundaries.md`](../../10-architecture/module-boundaries.md) for the MODULE.toml schema and [`module-registry.md`](../../10-architecture/module-registry.md) for the nav entry it produces.

## Scope

**In scope:**
- Rust helper in `src-tauri/src/modules.rs`: reads every `modules/*/MODULE.toml` at app startup, returns a typed struct per module.
- Tauri command `list_modules()`: exposes the scanned list to the frontend.
- Validation: required fields present (`name`, `display_name`, `version`, `nav.order`, `nav.route`), correct types. Fail soft — invalid MODULE.toml → log error, include module with `available: false`.
- Fixture test: a `modules/_fixtures/valid/MODULE.toml` and `modules/_fixtures/invalid/MODULE.toml` loader round-trip in Rust tests.

**Out of scope:**
- Actually mounting module code — that's task 0002 and each module's own tasks.
- Validating that the paths declared in MODULE.toml (entrypoints, frontends) exist on disk. This is purely schema validation for v0.2.

## Files to touch

- (NEW) `src-tauri/src/modules.rs`
- `src-tauri/src/lib.rs` — expose `list_modules` command; wire into invoke handler
- (NEW) `src-tauri/tests/modules_test.rs` — fixture-based round trip
- (NEW) `modules/_fixtures/valid/MODULE.toml`
- (NEW) `modules/_fixtures/invalid/MODULE.toml`

## Acceptance criteria

- [ ] `cargo test --manifest-path src-tauri/Cargo.toml modules_test` passes.
- [ ] Valid fixture loads into a struct with all expected fields.
- [ ] Invalid fixture returns a typed error with actionable message.
- [ ] Calling `invoke('list_modules')` from the frontend console returns an array (may be empty if no real modules exist yet).
- [ ] Adding a malformed `MODULE.toml` to `modules/_fixtures/` produces a WARN log but does not crash the sidecar.

## Implementation notes

- Use `toml` crate (already common in Rust ecosystem — add to Cargo.toml).
- Do NOT re-parse on every `list_modules` invocation; cache at app startup, refresh on a dedicated `refresh_modules` command (stub for now, full impl post-v0.2).
- The `_fixtures/` directory is explicitly not scanned by the real loader in production — guard with a path filter that excludes directories starting with `_`.

## Verification commands

```bash
cd src-tauri && cargo test modules_test
cd src-tauri && cargo check
bun run dev   # manual: open devtools, run await window.__TAURI__.invoke('list_modules')
```

## Status updates

- 2026-04-15 (planning): created.
- 2026-04-17 (claude): verified. `src-tauri/src/modules.rs` implements the loader; `src-tauri/tests/modules_test.rs` exercises the valid/invalid fixtures under `modules/_fixtures/`. `cargo test modules_test` → 5/5 passing. `list_modules` + `refresh_modules` registered in `lib.rs` `generate_handler!` Core group. Status `ready → done`.
