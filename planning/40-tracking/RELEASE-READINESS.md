# Release Readiness Charter — v0.2

**Last updated:** 2026-04-18
**Applies to:** ALOS-Desktop + QuantAmp v0.2 and all later release candidates.

This charter defines what "ready for release" means. ALOS must not ship because
the shell launches, the build passes, or the core surfaces mount. It ships only
when the product is fully wired, tested, documented, and honest about every
module's state.

## Release Principle

Do not rush. ALOS is a local-first agentic operating environment, not a demo
shell. A release candidate must prove that the modules, bridges, runtime,
packaging, and safety controls work together under realistic user flows.

No task may mark v0.2 shippable by accepting placeholders, mocked surfaces, or
"known broken but acceptable" behavior unless the user explicitly approves that
exception in writing and the exception is recorded in this file.

## Required Gates

All gates below must pass before v0.2 is called a release candidate.

### 1. Build And Test Gate

- `npx tsc -b --noEmit` exits 0.
- `npm run build` exits 0.
- `cd src-tauri && cargo check && cargo fmt --check && cargo test` exit 0.
- `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/` exits 0.
- The root JavaScript test command is scoped so it tests ALOS-owned code, not
  scratch or vendored GitNexus suites by accident.

### 2. Packaging Gate

- `npm run tauri build` produces a launchable `.app`.
- The packaged `.app` spawns the frozen Python sidecar from bundled resources.
- Quitting ALOS leaves no orphaned backend or PTY processes.
- First-run auth/bootstrap works from the packaged app context and does not ask
  users to run ambiguous source-tree commands against the wrong data directory.
- DMG packaging is green. v0.2 requires a working DMG before release candidate
  status, though the fix may be sequenced after higher-risk product/runtime
  blockers.

### 3. End-To-End Product Gate

The manual smoke test must exercise the app as a user would:

- Fresh `~/.alos` setup.
- Provider validation and config persistence.
- Auth/login.
- Root shell and activity bar.
- Chat.
- Forge editor, file tree, save path, search, source control panel, and PTY.
- Current workflow create/save/publish/execute/approve/audit flow.
- Atlas repository register/index/search/impact flow.
- Chamber session list/run/stop flow.
- Tray hide/show/quit.

Screenshots and logs are required for every major transition.

### 3A. Core Product Capability Gate

v0.2 is not a shell release. The following capabilities must be complete before
packaging or smoke testing can be treated as meaningful:

- Chat is a frontier-grade authenticated chat experience, at least restoring the
  quality of the prior browser/web-app chat: streaming, history, rich message
  rendering, run/plan visibility, approval controls, stop controls, reconnect
  recovery, and no placeholder copy.
- Forge is a complete programming environment for solo user programming,
  user-led agent-assisted programming, and ALOS autonomous programming with
  appropriate approval and Chamber verification before disk writes.
- Current is a complete workflow environment for solo workflow making, user-led
  agent-assisted workflow making, and ALOS autonomous workflow orchestration as
  part of operations.
- Atlas is an interactive visual file map and dependency consequence interface
  that users can inspect and agents can naturally use during planning, impact
  analysis, and implementation. Atlas is expected to be a proprietary upgraded
  successor to the GitNexus concept, not a weaker placeholder.
- Chamber is the pre-write proving ground for agent work. Agents complete build
  and test tasks in Chamber before writing to disk unless the user explicitly
  approves an audited exception.
- Settings are robust enough for normal users: provider setup, original-admin
  setup/recovery, runtime/workspace configuration, diagnostics, and safety
  controls do not require hidden terminal knowledge for ordinary use.

### 4. Integration Gate

Every intended v0.2 bridge must be real, not only scaffolded:

- Frontend events can reach the Python event bus.
- Python/module events can reach the frontend event bus.
- Agent runtime can invoke Current's `invoke_agent` node and record events.
- Agent runtime can use Atlas MCP tools for dependency and impact analysis.
- Forge file and terminal actions are observable by the agent/runtime layer.
- Chamber gates agent writes through build/test evidence before disk mutation.
- Current, Forge, Atlas, and Chamber use the ALOS sidecar/API contract, not
  old standalone ports or Rex-era env vars.

### 5. Dependency Intelligence Gate

Before release, produce a full dependency and blast-radius map for the ALOS
release-critical flows. Atlas is the product capability under evaluation here.
External GitNexus MCP access is useful audit tooling for agents, but it is not
part of the ALOS build and must not be treated as a release blocker.

Minimum required output:

- Module dependency map: shell, Rust core, Python sidecar, Forge, Current,
  Atlas, Chamber, and Chat.
- Symbol/process impact map for release-critical flows.
- List of d=1 direct dependents for every edited release-critical symbol.
- Known gaps where Atlas is not yet at GitNexus parity.
- Regression test recommendations from the graph.

If external GitNexus MCP resources are unavailable, continue with filesystem,
local CLI, and Atlas evidence. Do not block the release plan on Codex-side MCP
configuration.

### 6. Rebrand And Product Honesty Gate

- No `RexCode`, `RexFlow`, `RexNexus`, `RexBot`, or `RexHub` references outside
  `Upgrades From Rex/` and `planning/`.
- UI copy must describe what works now. It must not imply placeholder features
  are complete.
- Module names must match `planning/00-overview/naming.md`.

### 7. Documentation Gate

- `README.md` describes ALOS, not the Vite template.
- `BUILD.md` and release instructions match the actual build path.
- Planning docs identify remaining v0.3 work without hiding v0.2 gaps.
- Every shipped feature has a verification command or manual test path.

## No-Go Conditions

Any item below blocks release:

- Packaged app cannot start its backend.
- Packaged app reaches auth but cannot provide a clear, verified first-run admin
  key path.
- A core module mounts but cannot use its own backend contract.
- Chat cannot perform a real authenticated agent interaction through the
  backend session/WebSocket contract at frontier-grade UX quality.
- Forge cannot support solo, assisted, and autonomous programming through the
  ALOS runtime.
- Current cannot support solo, assisted, and autonomous workflow orchestration
  through the ALOS runtime.
- Atlas cannot provide a visual interactive file/dependency map, consequence
  queries, and agent-usable dependency intelligence for this repository.
- Chamber cannot require build/test completion before agent writes reach disk.
- Settings cannot support provider setup, original-admin setup/recovery,
  diagnostics, and safety controls without terminal-only workflows.
- User approval gates are bypassed for destructive actions.
- The official test commands fail for ALOS-owned code.
- The app leaves orphaned child processes after quit.

## Exceptions

Exceptions require explicit user approval and must be recorded here with:

- Date.
- Exact feature or gate waived.
- Why it is acceptable.
- User-facing release note text.
- Follow-up task ID.

No exceptions are approved as of 2026-04-18.
