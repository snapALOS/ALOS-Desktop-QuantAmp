# Module Boundaries

**The rule:** a module is a black box. The outside world sees its contracts; the inside is the module's business.

## Directory layout (locked)

```
ALOS-Desktop/
  modules/
    forge/
      frontend/            # React, owns its routes under /forge
        package.json       # its own manifest
        src/
      backend/             # Python, owns its routes under /api/forge
        pyproject.toml     # its own manifest
        src/alos_forge/
      contracts/           # public surface (typed)
        events.ts
        commands.ts
        python.py
      tests/
      README.md
      MODULE.toml          # module metadata (see below)
    current/
      ... same shape ...
    atlas/
      ... same shape ...
```

## MODULE.toml (per module)

```toml
[module]
name = "forge"
display_name = "ALOSForge"
version = "0.2.0"
description = "Agentic IDE shell."

[capabilities]
provides = ["editor", "terminal", "file-tree", "lsp-client"]
requires = []  # modules this one depends on; empty = standalone-capable

[nav]
order = 10
icon = "code"
route = "/forge"

[contracts]
events = "contracts/events.ts"
commands = "contracts/commands.ts"
python = "contracts/python.py"

[standalone]
# Reserved for post-v1 standalone-mode packaging.
# v0.2 leaves these unused but validated.
entrypoint = "backend/src/alos_forge/__main__.py"
frontend_port = 5174
```

## Hard-isolation rules

1. **A module may not import another module's internals.**
   - ❌ `from alos_atlas.storage import SQLiteGraph`
   - ✅ `from alos_atlas.contracts import Impact, ImpactRequest` *(contracts only)*

2. **Cross-module communication uses one of:**
   - **Events** (fire-and-forget, typed payloads) — published to the shell event bus.
   - **Commands** (request/response) — typed RPC via the shell's command router.
   - **MCP tools** — for agent-facing surfaces only.

3. **Each module owns its own persistence.** No shared database. Atlas owns `~/.alos/atlas.sqlite`, Current owns `~/.alos/current.sqlite`, etc.

4. **A module failing to load must not crash others.** The shell catches module init errors and shows a degraded nav entry (grayed out, "Unavailable — click for details").

5. **No shared global state.** No module-to-module singletons. If two modules need the same data, one owns it and the other reads via a contract.

## Dependency direction (enforced)

```
modules/*  →  core (shell, sidecar framework, sandbox)

modules/*  ↛  modules/*        # never (direct)
modules/*  ⇄  contracts/*      # yes (via shell event bus / command router)
```

A lint check in CI greps for `from alos_<module>\.` imports inside other modules' source dirs and fails the build if it finds any.

## Why "hard" and not "soft"

The user's stated reason: if an agentic IDE corrupts one module's code, it should be able to **delete and regenerate just that module's files** without touching the rest. That requires:

- Self-contained manifests (so `rm -rf modules/forge/ && regenerate` works).
- No cross-imports (so the rest compiles without `forge/`).
- Contract-only coupling (so regeneration preserves the API).

## Grep checks (run before commit)

```bash
# No module imports another module's internals
grep -rn --include='*.py' -E 'from alos_(forge|current|atlas|cortex|reflex)\.' modules/ | grep -v '/contracts/' | grep -v 'modules/\1/'

# No module references another module's directory path
grep -rn --include='*.ts' --include='*.tsx' "modules/(forge|current|atlas)/(?!contracts)" modules/
```

Both should return zero matches. Wire them into a pre-commit hook after v0.2 ships.
