# ALOSCurrent — Rebrand Checklist

## String-replacement table

| Find (case-insensitive) | Replace with |
|---|---|
| `RexFlow` | `ALOSCurrent` |
| `rexflow` (identifier) | `alos_current` (Python) or `alosCurrent` (JS) |
| `rex-flow` | `alos-current` |
| `Rex Flow` | `ALOS Current` |
| `RexHub` | **delete related code** (no ALOS equivalent in v0.2) |
| `rexhub` (identifier) | **delete related code** |
| `rexbot` / `RexBot` | `ALOS` or drop, context-dependent |

## Path changes

| Old | New |
|---|---|
| `~/.rexflow/` | `~/.alos/current/` |
| `~/.rexflow/rexflow.sqlite` | `~/.alos/current/current.sqlite` |
| `/api/workflows/*` | `/api/current/workflows/*` |
| `/api/executions/*` | `/api/current/executions/*` |
| `/webhook/{path}` | `/api/current/webhook/{path}` |
| `/api/triggers/rexhub` | **delete** (replaced by event-bus subscriber) |
| `/api/schedules/run` | `/api/current/schedules/run` |

## Package / identifier changes

- Python package: `rexflow_server` → `alos_current`.
- npm package (internal): `@rexflow/ui` → `@alos/current-ui`.
- CLI: `rexflow-server` → **deleted** (no standalone binary in v0.2).
- Default port: 8770 → **deleted** (mounted under sidecar port).
- Auth header: `x-rexflow-token` → **deleted** (no auth in v0.2, planned for v0.3).

## User-facing strings

- Module name (activity bar): `Current`.
- Full name shown in Designer header: `ALOSCurrent`.
- Empty-designer text: "Start building a workflow with ALOSCurrent."
- Settings tab: "ALOSCurrent Settings."
- Audit log entries: no RexFlow references in freshly written rows. (Old rows in `~/.rexflow/` are not migrated; dev data is wiped on rebrand.)

## Node type renames

- `assign_department_head` → `invoke_agent` (with `agent_id="supervisor"` config).
- `assign_sub_agent` → `invoke_agent` (with specified `agent_id`).
- `escalation_gate` → `escalation_gate` (kept; wires to ALOS approval UI).
- `rexhub_trigger` → `alos_event_trigger`.

Store a one-time migration for existing `.json` workflow exports in `modules/current/backend/src/alos_current/migrations/v0_2_0_rename.py` so anyone with a vendored workflow file can `current migrate workflow.json` and get the renamed version. This is the only CLI verb v0.2 keeps.

## Verification grep (must return zero outside `_vendor/`)

```bash
grep -rni --include='*.{ts,tsx,py,rs,md,json,toml,yaml,yml,css,scss,html,sql}' \
  -E '\b(rexflow|rex-flow|rexhub|rex_flow|rex_hub)\b' \
  modules/current/ src/ src-tauri/ backend/ | grep -v '/_vendor/'
```

Acceptance: zero matches after Phase 7.
