# ALOS Desktop — Conventions

**Audience:** every human and agent that writes code in this repo.
**Rule:** inspect existing code before writing new code. Match what's already there. This document is the tiebreaker when "what's already there" is ambiguous or missing.
**Scope:** v0.x. Locks tighter at v1.0.

---

## 0. The meta-rule

When in doubt, **grep for 2 similar files, mimic them exactly**. Don't invent a style.

If two existing files disagree, follow this document. If this document doesn't answer, pick the option that minimizes diff against the majority pattern in the affected directory.

---

## 1. Repository layout (reminder)

```
ALOS-Desktop/
├── src/                    # React frontend (TypeScript, Tailwind 4, shadcn-style)
├── src-tauri/              # Rust core (Tauri 2)
├── backend/                # Python sidecar (FastAPI + LangGraph)
├── scripts/                # build + maintenance helpers
├── modules/                # hard-isolated modules (v0.2+): forge, current, atlas
├── planning/               # single source of truth for design and tasks
├── Upgrades From Rex/      # vendored, pre-fold sources (read-only reference)
├── CONVENTIONS.md          # this file
├── README.md
└── BUILD.md
```

Never add a top-level directory without an RFC in `planning/30-rfcs/`.

---

## 2. Git

- **The repo is not yet a git repository at time of writing.** The first agent that needs git runs `git init && git add -A && git commit -m "Initial commit: ALOS Desktop v0.1 + v0.2 planning bundle"`.
- **Branch naming:** `task/NNNN-short-slug` where NNNN matches the task file in `planning/40-tracking/tasks/`.
- **Commit message:**
  - Subject: imperative mood, ≤ 72 chars, no trailing period. Prefix with the task id in brackets: `[0002] add ActivityBar skeleton`.
  - Blank line.
  - Body (optional but expected for non-trivial changes): wrap at ~72, explain **why**, not **what**. Reference the task file: `See planning/40-tracking/tasks/0002-module-registry-activity-bar.md`.
  - **Do NOT include marketing footers, co-authored-by, or "Generated with X" lines.** Clean history.
- **One task per PR.** If a PR touches more than one task, split it.
- **Never force-push to `main`** once `main` exists. Feature branches can rebase freely before merge.
- **Never skip hooks** (`--no-verify`) without justification in the PR description.
- **Never amend a commit that has been pushed.** Create a new commit.

---

## 3. TypeScript (`src/**`)

### Config (do not change without RFC)

- TS ~6.0, `verbatimModuleSyntax: true`, `noUnusedLocals/Parameters: true`, `erasableSyntaxOnly: true`, `jsx: react-jsx`.
- Module resolution is `bundler`. `@/*` path alias maps to `./src/*`.
- Target ES2023, DOM + DOM.Iterable lib.

### Style (match existing code)

- **No semicolons.** Single quotes. Two-space indent. Trailing commas on multi-line.
- **Imports** grouped in this order, each group separated by a blank line:
  1. Node/third-party (`react`, `zustand`, `@tauri-apps/api`, `lucide-react`).
  2. `@/...` aliased internal imports.
  3. Relative imports (`./…`, `../…`).
- **Type-only imports must use `import type`** — `verbatimModuleSyntax` enforces this. Mixing runtime + type imports requires splitting.
- **React:** function components only, `export default function Name() { ... }` for the file's primary component; named exports for secondary components in the same file.
- **Hooks:** custom hooks live in `src/hooks/` (or `modules/<m>/frontend/src/hooks/`), named `useFoo.ts`, file name matches the hook.
- **State:** Zustand for non-trivial shared state; `useState`/`useReducer` for local. Selector pattern: `const x = useStore((s) => s.x)`. Never destructure the whole store.
- **Effects with async:** wrap in `;(async () => { ... })()` inside `useEffect` with a `cancelled` flag for cleanup. See `src/App.tsx` for the canonical shape.
- **Naming:** PascalCase types/classes/components, camelCase functions/variables/hooks, SCREAMING_SNAKE_CASE constants.
- **Errors:** throw typed error classes, never bare strings. See `ApiError` in `src/api/client.ts`.

### Banned

- `any` — use `unknown` and narrow, or write the type. If you absolutely need `any`, add `// eslint-disable-next-line @typescript-eslint/no-explicit-any -- <reason>`.
- `// @ts-ignore` without a reason. Prefer `// @ts-expect-error -- <reason>`.
- `console.log` in committed code (use the app logger; `console.debug` for genuinely temporary dev-only logging is fine, but flag in PR).
- Inline styles (`style={{ ... }}`) for anything that should be a class. Use Tailwind utilities.
- New dependencies without an RFC.

### Comments

- Top-of-file block comment (`/** ... */`) on any file exporting a public API or implementing a non-obvious state machine. See `src/App.tsx` and `src/api/client.ts` for the canonical shape.
- Single-line comments (`//`) for local rationale; keep them useful — no "increment i" noise.

### UI

- **Tailwind 4** is the styling engine. Design tokens live in `src/index.css` under `@theme { ... }`.
- **Do not** import a CSS file per component. Compose Tailwind utilities inline.
- **shadcn-style primitives** live in `src/components/ui/`. When a new primitive is needed, add it under `ui/` and consume it everywhere — never re-roll.
- **Colors:** use the design tokens (`bg-background`, `text-foreground`, `border-primary`). No raw hex in JSX.
- **Icons:** `lucide-react`. Don't add a second icon library.
- **Accessibility:** every interactive element has an accessible label (button text, `aria-label`, or `<label htmlFor>`). Non-button clickables require `role` and keyboard handling.

---

## 4. Python (`backend/**` and `modules/*/backend/**`)

### Config

- Python **3.9+** baseline (note: we use typing module types, not the 3.10+ `|` union syntax).
- Ruff configured in `backend/pyproject.toml`: line-length 120, target `py39`.
- Pytest configured; tests live in `backend/tests/` (shared) and `modules/<name>/backend/tests/` (module-local).

### Style

- **Always** start files with `from __future__ import annotations`. This is non-negotiable — it's in every existing file and enables forward-reference type hints.
- **Type hints on every function signature** — including internal helpers. Use `typing.Optional`, `typing.List`, `typing.Dict` etc., not `str | None` (py39 compat).
- **Pydantic v2 models** (`BaseModel`, `Field`) for structured data. No plain dataclasses for data crossing an IPC boundary.
- **Docstrings** use triple-double-quotes. First line is a one-sentence summary. Longer docstrings structure with blank-line-separated sections. See `backend/src/agents/capabilities.py::RoutingDecision` for the canonical style.
- **Module-level docstring** at the top of every new file. Short paragraph explaining what lives in this module.
- **Constants:** UPPER_SNAKE_CASE at module scope. Paired doc-comment above explaining what the constant means and why its value is what it is. See `AMBIGUITY_EPSILON` in `capabilities.py`.
- **Naming:** `snake_case` functions/variables, `PascalCase` classes, leading underscore for private helpers.
- **Imports:**
  1. `from __future__ import annotations`
  2. stdlib
  3. third-party
  4. local (`from src.X` in the core, `from alos_<module>.X` in module packages)
  Each group separated by a blank line. Alphabetical within group.

### Errors

- No bare `except:`. Always `except <SpecificError>:` or `except Exception as e:`.
- No swallowed exceptions. If you catch, log with context or re-raise a typed error.
- Custom exceptions inherit from a module base class (e.g., `CapabilityPolicyViolation`).

### Logging

- Use `logging.getLogger(__name__)` at module top; do not use `print`.
- Log levels: `DEBUG` for development noise, `INFO` for lifecycle events, `WARNING` for recoverable issues, `ERROR` for failures requiring attention.

### Tests

- Every new contract has a smoke test **in the same PR**. Tests live in `backend/tests/unit/` (core) or `modules/<name>/backend/tests/` (module).
- Test files named `test_<subject>.py`. Test functions named `test_<scenario>__<expectation>()` (two underscores separating scenario from expected outcome).
- **Use the supervisor/routing test file as the canonical style reference** — see `backend/tests/unit/test_routing.py`.
- No network in unit tests. Mock IO at the boundary.

### Banned

- `from typing import *` — enumerate imports.
- Mutable default arguments (`def f(x=[]):`).
- `os.path` for new code — use `pathlib.Path`.
- Global mutable state outside clearly-documented singletons (e.g., the performance counters in `capabilities.py`, which are intentional and documented).

---

## 5. Rust (`src-tauri/**`)

### Config

- Edition 2021, MSRV `1.77.2`.
- `cargo fmt` must be clean. `cargo clippy -- -D warnings` must be clean before merge.

### Style

- **Module-level doc comments** using `//!` at the top of every non-trivial file, with a purpose paragraph and a bulleted "Responsibilities" section. See `src-tauri/src/backend.rs` for the canonical style.
- **Item doc comments** with `///` on public items (structs, fns, consts).
- **Errors:** use `anyhow::Result` internally; map to `Result<T, String>` at `#[tauri::command]` boundaries with `.map_err(|e| format!("{e:#}"))`. See `launch_backend` in `backend.rs`.
- **Context on errors:** use `.context("…")` liberally from `anyhow::Context`. Error messages should tell the user what was happening when it failed.
- **Globals:** `static NAME: Mutex<Option<T>> = Mutex::new(None);` for lazy singletons. Don't use `lazy_static!`.
- **Naming:** snake_case fns/modules, PascalCase types, SCREAMING_SNAKE_CASE consts.
- **Imports** ordered: std → third-party → local. Grouped with blank lines.

### Banned

- `.unwrap()` in production paths (tests OK). Use `?` + context.
- `.expect("...")` in production paths except at `main()`-equivalent startup where failure is fatal and the message is informative (see `expect("error while building tauri application")` in `lib.rs`).
- `println!` / `eprintln!` — use `log::info!` / `log::error!` etc.
- `unsafe` without a block comment explaining why it's needed and what invariants it depends on.

### Tauri command boundary

- Every `#[tauri::command]` has:
  - A doc comment on the function.
  - A typed return (`BackendStatus`, `PreflightReport`, …) — never `serde_json::Value`.
  - String-mapped errors at the boundary.
  - Registration in `src-tauri/src/lib.rs` inside the `invoke_handler![]` list.

### Module commands

**Module commands** are `#[tauri::command]` functions owned by a specific module. They follow the naming rule `<module_id>_<verb>_<object>` (all snake_case), e.g. `forge_open_file`, `atlas_impact_symbol`, `current_trigger_workflow`.

- Module commands live in `src-tauri/src/<module_id>/commands.rs` (one file per module; create the `<module_id>/` module directory when the first command lands).
- Every module command is registered in `src-tauri/src/lib.rs` inside a labeled comment block (`// <ModuleName>`). Adding a command means adding exactly one line inside the right block.
- Module command **names** must match the naming rule. A reviewer who sees `atlas_dothing` in the handler list but no `atlas_` prefix elsewhere should block the PR.
- Core commands (owned by the shell, not by a module) do not carry a module prefix. Examples: `backend_status`, `preflight_check`, `list_modules`.

---

## 6. Contracts (`src/contracts/`, `modules/*/contracts/`)

- **Contract files are the stable API surface.** Treat changes to them the way you'd treat changes to a library's public API.
- Every contract file has a header comment:
  ```ts
  // CONTRACT VERSION: N
  // LAST CHANGED: YYYY-MM-DD
  // BREAKING CHANGES ALLOWED THROUGH: v0.x. LOCKED at v1.0.
  ```
- Adding a field or a new event variant is additive. Removing or retyping a field/variant is breaking.
- Breaking changes to a contract require an RFC.

---

## 7. Planning docs (`planning/**`)

- Markdown only. Mermaid diagrams are fine; ASCII diagrams are preferred for small topologies (paste-safe in any viewer).
- When you change architecture, update the doc **in the same commit** as the code. Task files must list the doc change in their acceptance criteria.
- **Never delete a planning doc.** Mark as superseded with a `status: superseded_by: XXXX` frontmatter field if it's an RFC; otherwise leave a pointer at the top.
- Keep prose tight. These docs are read by agents on every session — every extra paragraph is a tax.

---

## 8. Naming drift — the cardinal sin

The dead names (RexCode, RexFlow, RexNexus, RexBot, RexHub) must not appear in new code outside `Upgrades From Rex/` and `planning/`.

Before opening a PR, run:

```bash
grep -rni --include='*.{ts,tsx,py,rs,md,json,toml,yaml,yml,css,scss,html,sql}' \
  -E '\b(rexcode|rex-code|rex code|rexflow|rex-flow|rexnexus|rex-nexus|rexbot|rexhub)\b' \
  modules/ src/ src-tauri/ backend/ scripts/ \
  | grep -v '/_vendor/' | grep -v '/Upgrades From Rex/' | grep -v '/planning/'
```

Expect zero lines.

---

## 9. Module hygiene

From `planning/10-architecture/module-boundaries.md`:

- A module never imports another module's internals. Only contracts.
- A module owns its own persistence.
- A module's failure mode is "grayed out in the nav," not "crash the app."
- Cross-module communication goes through events, commands, or MCP tools — never direct calls.

Enforcement greps (must return zero):

```bash
# Python cross-module internal import
grep -rn --include='*.py' -E 'from alos_(forge|current|atlas|cortex|reflex)\.' modules/ \
  | grep -v '/contracts/' | grep -v 'modules/\1/'

# TS cross-module path reference
grep -rn --include='*.ts' --include='*.tsx' -E '@/../modules/(forge|current|atlas)/(?!contracts)' modules/
```

---

## 10. When a convention isn't covered here

1. Read three similar files. If they agree, follow them.
2. If they disagree, pick the newest one (by file age) and follow it.
3. If you had to make a judgment call, note it in the PR description so future readers see the reasoning.
4. If the same judgment call comes up twice, add it to this document in the same PR as the second occurrence.

---

## 11. Agent handles (for status updates and git author fields)

When agents log activity in task files or commit messages:

- Claude: `claude`
- Gemini 3 Flash (via Antigravity): `gemini-3-flash`
- Codex: `codex`
- A human contributor: `human:<first-name>`

Task file status-update lines use the format `- YYYY-MM-DD (<handle>): <verb> <object>`.

---

## 12. The three questions before every PR

1. **Does `grep` show zero dead-name matches?** (see §8)
2. **Do the formatters + linters pass?** `bun run lint`, `cd backend && ruff check .`, `cargo fmt --check`, `cargo clippy -- -D warnings`.
3. **Does the task file's acceptance checklist all check off mechanically, not aspirationally?**

If any answer is no, don't open the PR.
