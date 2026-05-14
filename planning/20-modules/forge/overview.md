# ALOSForge — Overview

**Canonical name:** ALOSForge  
**Dead name:** RexCode  
**Source:** `Upgrades From Rex/rexcode proprietary-ide/`  
**Target location:** `modules/forge/`  
**Tagline:** "The agentic IDE. Where agents read, write, and run your code."

## What it is

A fully-featured, VS Code-style IDE shell embedded in ALOS. Monaco editor, xterm.js terminal backed by portable-pty, file tree, command palette, extensions panel. Already production-shaped in the source repo.

## Why it's in v0.2

ALOS needs a working surface for agents and users to meet. A chat window + tool calls is not an IDE. Forge is the working surface — the place where an agent's "let me refactor `utils.py`" actually means *the file opens, the diff shows, the user accepts, the buffer updates, the test runs in the terminal below*.

## Key capabilities (v0.2)

| Capability | Status in source | Change needed for ALOS |
|---|---|---|
| Monaco editor | Works | None |
| File tree + workspace folders | Works | Rename `.rex*` → `.alos*` files; swap default theme |
| xterm.js + portable-pty terminal | Works | None |
| Command palette | Works | Rewire commands to ALOS IPC |
| Extensions panel | Hardcoded demo data | Preserve as-is for v0.2 (user ask) |
| LSP client | Partial (stubs) | Complete per [lsp-integration.md](../../10-architecture/lsp-integration.md) |
| Agent observation hook (`isAgentObserving`) | Stub | Implement against ALOS agent runtime |
| `TauriAdapter` / `HubAdapter` environment split | Works | Keep only `TauriAdapter` for v0.2; drop HubAdapter (user deferred) |

## What is NOT in v0.2 from Forge

- Standalone-mode (HubAdapter path). Deferred to post-v1.
- Remote workspaces.
- Git UI panel beyond what Monaco gives (diff, inline). A dedicated source-control panel is v0.3+.
- Custom extension API. Extensions panel shows hardcoded demos only.

## Surfaces

### Frontend
- Mount point: `/forge` route, active-module slot in the shell.
- Owns its own routing inside the slot (`/forge/editor/*`, `/forge/terminal/*`).
- Mono package: `modules/forge/frontend/`.

### Backend
- Python: file operations, workspace indexing hooks, pty management on Unix fallback. (Primary pty path is portable-pty via Rust; Python fallback is for features Rust-side can't do trivially.)
- Routes under `/api/forge/*` (see [ipc-contracts.md](../../10-architecture/ipc-contracts.md)).

### Events emitted
- `forge.file.changed`
- `forge.file.saved`
- `forge.workspace.opened`
- `forge.workspace.closed`
- `forge.terminal.spawned`
- `forge.terminal.exited`

### Events consumed
- `atlas.index.complete` (to refresh code-lens hints in editor)
- `current.workflow.completed` (to surface results in the status bar when a workflow that edited files completes)

### Agent-facing tools (MCP)
- `forge_open_file(path)` — opens a file in the editor; returns buffer id.
- `forge_apply_diff(path, diff)` — proposes a diff; returns a diff id the user must accept.
- `forge_read_file(path)` — reads current buffer (may differ from disk if unsaved).
- `forge_run_command(command, workspace)` — runs in a new observed pty; returns run id.
- `forge_get_selection()` — returns current editor selection for context.

All `forge_apply_diff` and `forge_run_command` calls are `risk: "high"` and require user approval in the frontend.

## Dependencies on other modules

- **Atlas** (optional): code-lens impact hints in gutter. Forge works without Atlas; just no hints.
- **Current** (optional): status-bar workflow state. Forge works without Current.
- **LSP supervisor** (required): all code intelligence.

## Risk & unknowns

- Portable-pty on Windows needs testing; the source repo may have macOS-biased assumptions.
- Monaco bundle size may push Tauri webview past comfort on first load; consider lazy-loading language workers.
- HubAdapter removal must not leave dangling imports. Audit before merge.
