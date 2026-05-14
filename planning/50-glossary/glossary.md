# Glossary

**Alphabetical. One definition per term.** If a term appears in code or docs and isn't here, add it before merging.

---

### Activity bar
The narrow vertical bar on the far left of the ALOS window (VS-Code-style) holding one icon per module. Distinct from a module's own internal sidebar. See [10-architecture/module-registry.md](../10-architecture/module-registry.md).

### Agent
A configured LLM persona running inside LangGraph with a capability set, risk profile, and tool allowlist. Routed to by the supervisor.

### Agent bridge
The collection of MCP tools that let agents drive Forge (open files, apply diffs, run commands). See [20-modules/forge/overview.md](../20-modules/forge/overview.md).

### ALOS
Autonomous Local Operating System. Always all-caps. Never "Alos."

### ALOS Desktop
The Tauri app. The repository is `ALOS-Desktop`; the product name is "ALOS Desktop" (with space) in prose.

### ALOSAtlas
Code intelligence graph module. Dead name: RexNexus.

### ALOSCortex
*(future)* Model management module. Dead name: AI Model Lab.

### ALOSCurrent
Workflow orchestrator module. Dead name: RexFlow.

### ALOSForge
Agentic IDE shell module. Dead name: RexCode.

### ALOSReflex
*(future)* Agent scenario / regression module. Dead name: Scenario Toolkit.

### Ambiguity epsilon
Routing scalar `0.5`: if the top two candidate agents score within epsilon, routing is ambiguous and the LLM fallback is consulted. See `backend/src/agents/capabilities.py`.

### Capability
A declared ability of an agent (e.g., `code_write`, `shell_exec`). Routing scores agents by capability match to the task.

### Contract
A file under `*/contracts/` that defines the public surface a piece of code exposes. Importing past a contract is a boundary violation.

### Current
Shorthand for ALOSCurrent. Use the short form only inside module-local code; prose uses "ALOSCurrent."

### DAG
Directed acyclic graph. Workflows in Current are DAGs.

### Dead name
A name we used to use and must never use again (RexCode, RexFlow, RexNexus, RexBot, RexHub). See [00-overview/naming.md](../00-overview/naming.md).

### EWMA decay
Exponentially-weighted moving average decay on per-agent performance counters. A successful completion halves the failed and tool_denied counts so early bad luck doesn't permanently bench an agent. See `backend/src/agents/capabilities.py::record_agent_completion`.

### Event bus
The pub/sub channel modules use to communicate without importing each other. Events are typed per `src/contracts/events.ts`.

### Extensions panel
The (currently hardcoded demo) extensions UI in Forge. Preserved through v0.2, real API in v0.3+.

### Forge
Shorthand for ALOSForge.

### HubAdapter
A second runtime target RexCode shipped with, separate from Tauri. **Deleted** in the v0.2 fold-in.

### Invoke_agent
A Current workflow node type that calls the LangGraph supervisor as a workflow step. See [10-architecture/agent-runtime.md](../10-architecture/agent-runtime.md).

### LangGraph
The agent turn engine. Runs one conversation / one job's worth of supervisor → worker → tool cycles.

### LSP
Language Server Protocol. Forge integrates several LSP servers for code intelligence. See [10-architecture/lsp-integration.md](../10-architecture/lsp-integration.md).

### MCP
Model Context Protocol. Mechanism agents use to call module tools. Each module that exposes agent-facing capabilities ships an MCP server.

### MODULE.toml
Per-module manifest at `modules/<name>/MODULE.toml`. Registry scans these to build the activity bar. See [10-architecture/module-boundaries.md](../10-architecture/module-boundaries.md).

### Module
A self-contained, hard-isolated subpackage under `modules/<name>/`. Owns its UI, backend, persistence, and contracts. v0.2 modules: Forge, Current, Atlas.

### Module registry
The runtime list of installed modules, generated from MODULE.toml scans. Drives the activity bar.

### Observed pty
A pseudo-terminal whose output stream is mirrored to both the user's terminal view and the agent's context. Agents can "see" what the commands they run produce.

### Preflight
The startup check that verifies Python, venv, and required packages before spawning the backend sidecar. See `src-tauri/src/preflight.rs`.

### Risk class
A tag on an MCP tool declaring how much damage it can do. `low` (read-only), `medium` (can trigger side effects), `high` (write/delete/exec). `high` requires user approval.

### Routing decision
A record of how the supervisor picked an agent for a turn. Includes method, candidate scores, epsilon comparison. Auditable.

### Sandbox
Cross-cutting runtime for isolated code execution. **Not** a module. See [20-modules/_future/sandbox.md](../20-modules/_future/sandbox.md).

### Sidecar
The PyInstaller-packaged Python runtime spawned by the Rust core. Hosts agent runtime + all module backends.

### Single-selection invariant
Per-turn guarantee that exactly one agent is selected, recorded, and invoked. Violations are routing bugs.

### Standalone mode
A module running outside ALOS as its own binary. **Not shipped in v0.2.** Preserved as a future-proofing constraint (hard module boundaries make it possible).

### Stickiness bonus
`+0.4` score boost to the currently-active worker so routing doesn't thrash mid-conversation.

### Supervisor
The LangGraph node that routes each turn. Implements capability scoring, ambiguity detection, and LLM fallback. Lives in `backend/src/graph/supervisor.py`.

### Task file
A markdown file under `planning/40-tracking/tasks/` describing one unit of work with acceptance criteria. Canonical scope record.

### Tauri
Rust + webview desktop app framework. ALOS Desktop is a Tauri 2 app.

### Tree-sitter
Incremental parser library used by Atlas for structural indexing.
