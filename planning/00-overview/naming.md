# Naming — LOCKED

**Do not drift. Any code, doc, commit, or task using a dead name is wrong and must be fixed.**

## Module names

| Canonical (ALOS) | Dead name (do not use) | Short code | Directory | Crate / pkg |
|---|---|---|---|---|
| **ALOSForge** | RexCode | `forge` | `modules/forge/` | `alos-forge` |
| **ALOSCurrent** | RexFlow | `current` | `modules/current/` | `alos-current` |
| **ALOSAtlas** | RexNexus | `atlas` | `modules/atlas/` | `alos-atlas` |
| **ALOSCortex** | AI Model Lab | `cortex` | `modules/cortex/` *(future)* | `alos-cortex` |
| **ALOSReflex** | Scenario Toolkit | `reflex` | `modules/reflex/` *(future)* | `alos-reflex` |

### Sandbox
Sandbox is **not** a module. It is a cross-cutting runtime capability baked into the core. No nav entry, no directory under `modules/`. It lives at `backend/src/sandbox/` and is consumed by any module that needs isolated execution.

## Product naming

- Product: **ALOS** (all caps). Never "Alos" or "ALOs".
- Desktop app: **ALOS Desktop** (with space in prose, `ALOS-Desktop` as repo/dir name, `ALOS_Desktop` in version strings).
- Version scheme: `ALOS_Desktop vMAJOR.MINOR.PATCH`. Stay in `v0.x` through dev/test. `v1.0` = commercial release.

## One-liner pitches (use verbatim in marketing copy)

- **ALOSForge** — "The agentic IDE. Where agents read, write, and run your code."
- **ALOSCurrent** — "Workflow orchestration for agents, tools, and humans. DAGs that think."
- **ALOSAtlas** — "A live map of your codebase. Agents grounded in facts, not guesses."
- **ALOSCortex** *(future)* — "Train, fine-tune, and swap models without leaving your IDE."
- **ALOSReflex** *(future)* — "Agent behavior under pressure. Scenarios, red-teaming, regressions."

## Renaming rules

- A rename requires an RFC in `30-rfcs/`.
- Renames must land in one commit that touches every occurrence.
- Do **not** add aliases ("also known as RexX"). Dead names stay dead.

## Grep for drift

```bash
# From repo root — should always return zero matches after rebrand lands
grep -rni --include='*.{ts,tsx,py,rs,md,json,toml}' -E '\b(rexcode|rexflow|rexnexus|rexbot|rexhub)\b' . | grep -v '/Upgrades From Rex/' | grep -v '/planning/'
```

The `grep -v` excludes the vendored-upgrade directory and this planning tree (which legitimately references the dead names for historical context).
