# Roadmap

## Version scheme

- `v0.x` — development and testing. Breaking changes allowed between minors.
- `v1.0` — first commercial release. Semver enforced from this point on.

## v0.1 — SHIPPED

- Agent swarm backend (LangGraph supervisor + workers).
- Capability-scored routing with ambiguity-gated LLM fallback, EWMA counter decay, single-selection invariant.
- Tauri 2 shell, React 18 frontend, PyInstaller sidecar, preflight gate.
- System tray (Show / Hide / Quit) with close-to-tray semantics.

## v0.2 — IN PLANNING (this bundle)

**Theme:** "The agentic IDE." Fold Forge + Current + Atlas into the shell.

**Release posture:** do not rush. v0.2 remains in active buildout until
the production readiness gate in
[`../40-tracking/RELEASE-READINESS.md`](../40-tracking/RELEASE-READINESS.md)
passes. A launchable shell or packaged `.app` is not enough.

**Scope (must ship):**
- [ ] `modules/` directory with hard-isolated subpackages (`forge/`, `current/`, `atlas/`).
- [ ] Second left-side VS Code-style nav bar for module switching.
- [ ] ALOSForge: Monaco, xterm, portable-pty, file tree, extensions panel preserved (hardcoded demo data OK).
- [ ] ALOSCurrent: DAG editor + execution + audit, embedded React SPA, SQLite persistence.
- [ ] ALOSAtlas: SQLite code graph + MCP server, bounded tool set exposed to agents.
- [ ] LSP integration: pluggable registry, ship pyright + typescript-language-server + rust-analyzer.
- [ ] Rebrand: zero occurrences of RexCode / RexFlow / RexNexus / RexBot / RexHub outside `Upgrades From Rex/` and `planning/`.
- [ ] Agent ↔ editor bridge (agent opens files, proposes diffs, user accepts/rejects).
- [ ] Agent ↔ terminal bridge (agent runs commands in an observed pty).
- [ ] All existing v0.1 tests still pass.
- [ ] Full release-readiness gate passes: packaging, end-to-end flows,
      integration bridges, dependency intelligence, rebrand honesty, and docs.

**Out of scope (deferred to later 0.x or v1.0):**
- Standalone-mode packaging for modules.
- Cortex and Reflex.
- BitNet.
- Multi-user.
- Cloud sync.

## v0.3 — TENTATIVE

- ALOSCortex scaffolding (model registry, no training yet).
- Workflow templates marketplace (local folder for now).
- Remote LSP support.

## v0.4 — TENTATIVE

- ALOSReflex scaffolding (scenario runner, agent regression tests).
- Cortex training loop.

## v1.0 — COMMERCIAL

- Semver locked.
- Standalone-mode packaging for Forge, Current, Atlas.
- Signed/notarized installers for macOS, Windows, Linux.
- Docs site.
- Telemetry (opt-in) and crash reporting.
