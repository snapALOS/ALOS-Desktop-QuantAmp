# ALOSAtlas — Rebrand Checklist

## String-replacement table

| Find (case-insensitive) | Replace with |
|---|---|
| `RexNexus` | `ALOSAtlas` |
| `rexnexus` (identifier) | `alos_atlas` / `alosAtlas` |
| `rex-nexus` | `alos-atlas` |
| `Rex Nexus` | `ALOS Atlas` |

## MCP tool renames

| Old | New |
|---|---|
| `impact` | `atlas_impact_symbol` |
| `change_scope` | `atlas_change_scope` |
| `recommend_tests` | `atlas_recommend_tests` |
| `symbol_context` | `atlas_symbol_context` |
| `file_context` | `atlas_file_context` |
| (new) | `atlas_index_status` |

## Path changes

| Old | New |
|---|---|
| `~/.rexnexus/` | `~/.alos/atlas/` |
| `~/.rexnexus/rexnexus.sqlite` | `~/.alos/atlas/atlas.sqlite` |
| `/api/nexus/*` | `/api/atlas/*` |

## Package / identifier changes

- Python package: `rexnexus` → `alos_atlas`.
- MCP server entry point: `rexnexus.mcp_server` → `alos_atlas.mcp_server`.
- CLI (internal): `rexnexus index` → `alos-atlas index` (if preserved; check if needed beyond dev).

## User-facing strings

- Module name (activity bar): `Atlas`.
- Full name in UI header: `ALOSAtlas`.
- Empty-state text: "ALOSAtlas is ready. Open a workspace in Forge to begin indexing."
- Status messages: "Indexing with ALOSAtlas…" (not RexNexus).

## Verification grep (must return zero outside `_vendor/`)

```bash
grep -rni --include='*.{ts,tsx,py,rs,md,json,toml,yaml,yml,css,scss,html,sql}' \
  -E '\b(rexnexus|rex-nexus|rex_nexus)\b' \
  modules/atlas/ src/ src-tauri/ backend/ | grep -v '/_vendor/'
```

Acceptance: zero matches after Phase 6.
