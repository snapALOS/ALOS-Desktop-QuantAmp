# ALOS Modules

Each subdirectory is a self-contained module with hard isolation.

## Layout

```
modules/
  <name>/
    MODULE.toml          # metadata — parsed by the shell at startup
    frontend/            # React, owns routes under /<name>
    backend/             # Python, owns routes under /api/<name>
    contracts/           # public typed surface (events, commands, MCP)
    tests/
```

## Rules

- A module **may not import** another module's internals — contracts only.
- Cross-module communication uses the **event bus** or **command router**.
- Each module owns its own persistence (separate SQLite).
- A module failing to load must not crash others.

See [`planning/10-architecture/module-boundaries.md`](../planning/10-architecture/module-boundaries.md) for the full spec.

## Directories starting with `_`

Directories prefixed with `_` (e.g. `_fixtures/`) are excluded from the module scanner and are used for testing only.
