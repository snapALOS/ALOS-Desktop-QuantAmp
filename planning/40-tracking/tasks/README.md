# Tasks

## Files in this directory

- `_template.md` — copy this to create a new task.
- `NNNN-slug.md` — individual task files.

## Status of the task set

v0.2 planning is in-flight. The table below lists every task referenced from integration plans, even ones that haven't been fully fleshed into a file yet. Fleshed-out files exist in this directory. Everything else is a stub: one line per task, waiting for someone to `cp _template.md NNNN-slug.md` and fill in the acceptance criteria from the integration plan.

**Rule:** before picking up an unfleshed task, first flesh it using the matching integration plan section, then move it through Ready → In Progress normally.

## Full task index (planned for v0.2)

### Core (0001–0009)

- [x] 0001 — Create modules/ directory and workspace manifests
- [x] 0002 — Build module registry and activity bar skeleton
- [x] 0003 — Define event bus contract and publish/subscribe helpers
- [x] 0004 — Add MODULE.toml loader and nav-entry generator
- [x] 0005 — Preserve v0.1 Chat surface as a built-in registry entry *(fleshed, ready)*
- [x] 0006 — Tauri command registration pattern for module-scoped commands *(fleshed, ready)*

### ALOSForge (0010–0029)

- [x] 0010 — Vendor source and produce INVENTORY.md
- [ ] 0011 — Scaffold `modules/forge/` layout and MODULE.toml *(fleshed from forge/integration-plan.md Phase 2)*
- [ ] 0012 — Move editor (Monaco) into `modules/forge/frontend/`
- [ ] 0013 — Move terminal (xterm + portable-pty) into `modules/forge/`
- [ ] 0014 — Rebrand pass: delete HubAdapter, rename files, verify grep clean
- [ ] 0015 — LSP supervisor (Rust) — spawn/health/restart
- [ ] 0016 — LSP bundling — stage pyright, ts-ls, rust-analyzer into resources
- [ ] 0017 — LSP frontend client — wire monaco-languageclient
- [ ] 0018 — Forge MCP tools (open_file, apply_diff, read_file, run_command, get_selection)
- [ ] 0019 — Diff acceptance UI
- [ ] 0020 — Observed pty (stream pty output to agent context)
- [ ] 0021 — Forge cleanup (delete _vendor, run drift grep)

### ALOSCurrent (0030–0049)

- [x] 0030 — Vendor source and produce INVENTORY.md
- [ ] 0031 — Scaffold `modules/current/` layout
- [ ] 0032 — Backend fold-in: move Python source, rename package, update paths
- [ ] 0033 — Implement `invoke_agent` node type (thread-pool wrapper, LangGraph adapter)
- [ ] 0034 — Mount Current HTTP API under sidecar `/api/current/*`
- [ ] 0035 — Frontend fold-in: move React SPA, convert standalone bootstrap to module mount
- [ ] 0036 — Frontend rebrand: wordmark, colors, routes
- [ ] 0037 — Frontend API client: point at same-origin `/api/current/*`
- [ ] 0038 — Event-bus triggers: `alos_event_trigger` node + shell-bus subscriber
- [ ] 0039 — Current MCP tools (list_workflows, trigger_workflow, get_run_status)
- [ ] 0040 — Current cleanup

### ALOSAtlas (0050–0069)

- [x] 0050 — Vendor source and produce INVENTORY.md
- [ ] 0051 — Scaffold `modules/atlas/` layout
- [ ] 0052 — Backend fold-in: move Python, rename package, change DB path
- [ ] 0053 — Rename MCP tools with `atlas_` prefix, wire capability gates
- [ ] 0054 — Tree-sitter bundling for Python/TS/JS/Rust
- [ ] 0055 — Event wiring: consume `forge.file.saved`, `forge.workspace.opened`; emit `atlas.index.*`
- [ ] 0056 — Diagnostic UI: status, progress, symbol lookup, re-index button
- [ ] 0057 — Atlas cleanup

### Agent bridge / global rebrand / docs (0090+)

- [ ] 0090 — Capability gate entries for all new MCP tools (Forge + Current + Atlas)
- [ ] 0091 — Approval UI for high-risk MCP tool calls
- [ ] 0100 — Global rebrand drift grep: zero matches across repo (modulo _vendor and planning)
- [✓] 0120 — CONVENTIONS.md for agent contributors (done — also produced AGENTS.md at repo root)

### Release hardening (0140+)

- [x] 0140 — Post-Antigravity remediation
- [x] 0141 — Install vendored module dependencies
- [x] 0142 — Vendored/verbatim module syntax
- [x] 0143 — End-to-end smoke test
- [ ] 0144 — Tauri release bundle dry run
- [ ] 0145 — Packaged Python sidecar not spawning
- [ ] 0146 — DMG bundle failure
- [ ] 0147 — Production readiness gate
- [x] 0148 — Packaged first-run auth/bootstrap UX
- [x] 0149 — Chat real agent interaction
- [x] 0150 — Forge IDE release hardening
- [x] 0151 — Current agentic workflow orchestration
- [x] 0152 — Atlas visual dependency intelligence
- [x] 0153 — Chamber pre-write build/test gate
- [x] 0154 — Robust settings interface
- [x] 0155 — Make ALOS logic processing engine frontier-grade

## When to flesh out

Flesh a task immediately before picking it up. Don't pre-flesh the whole backlog — some of these will need adjustment once earlier tasks reveal reality. The integration plans contain enough scope to flesh any of these in under 15 minutes.
