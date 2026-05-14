---
id: 0152
title: Atlas must provide visual dependency intelligence for users and agents
area: atlas
status: done
assigned_to: null
created: 2026-04-18
updated: 2026-04-18
effort: l
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0152 — Atlas must provide visual dependency intelligence for users and agents

## Context

Atlas is intended to be a proprietary, upgraded ALOS-native successor to the
GitNexus concept, not a lesser placeholder. GitNexus already has a visual
interface; Atlas must give users an inspectable visual file/dependency map and
must give ALOS agents a natural way to use that map during work.

## Scope

**In scope:**
- Register/index the current repository through Atlas.
- Render an interactive visual file map and dependency graph.
- Let the user inspect files, symbols, relationships, execution flows, and
  dependency consequences.
- Provide search and impact/consequence queries comparable to the GitNexus
  workflows used during development.
- Expose Atlas mapping/query capabilities to ALOS agents as structured tools or
  runtime context.
- Record known GitNexus-parity gaps and proprietary Atlas upgrades honestly.
- Integrate Atlas evidence into release-critical impact analysis.

**Out of scope:**
- External Codex-side GitNexus MCP configuration.
- Claiming full proprietary superiority without measurable user/agent-facing
  capabilities.

## Acceptance criteria

- [x] Atlas can index the ALOS repository from the desktop app or a documented
      local command path.
- [x] Atlas renders an interactive visual map of files and dependencies.
- [x] User can inspect direct and transitive dependency consequences for a file
      or symbol.
- [x] User can search by concept and jump from results to files/flows.
- [x] Agents can naturally call/use Atlas mapping during planning, editing, and
      impact analysis.
- [x] Atlas produces a dependency and impact report for release-critical ALOS
      flows.
- [x] Known gaps versus GitNexus visual/search/impact behavior are documented.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
env PYTHONPATH=.:backend:modules/atlas/backend/src python3.11 -m py_compile modules/atlas/backend/src/api/router.py backend/src/tools/atlas_tools.py modules/atlas/backend/src/alos_atlas/query.py modules/atlas/backend/src/alos_atlas/indexer.py
env PYTHONPATH=.:backend:modules/atlas/backend/src python3.11 -m pytest backend/tests
```

After code changes, the GitNexus index should be refreshed by the user with:

```bash
node scratch/git-nexus/gitnexus/dist/cli/index.js analyze --skip-git
```

Manual verification:

1. Open Atlas.
2. Index/register this repository.
3. Inspect a visual dependency path from shell to backend.
4. Run an impact/consequence query.
5. Confirm an agent can use the same Atlas evidence during a planned change.

## Status updates

- 2026-04-18 (codex): created from v0.2 clarification. Atlas is a release
  blocker until it is an interactive user-facing and agent-facing dependency
  intelligence system.
- 2026-04-18 (codex): completed Atlas desktop/backend/agent integration. Fixed
  the sidecar router import/config root, automatic repo registration during
  app indexing, authenticated Atlas endpoints, search/impact response
  normalization for the React view, and agent-tool Atlas home/default repo
  resolution. Verified route mounting, production frontend build, backend unit
  tests, Atlas agent tool registration, and a sample repo index/search/impact
  smoke test. Documented CLI usage, release-impact report commands, proprietary
  Atlas upgrades, and GitNexus parity gaps in `modules/atlas/docs/USING-ATLAS.md`.
