# Tracking System

**Purpose:** coordinate work across multiple agents and humans with no ambiguity, no double-work, no drift.

**Design constraint:** everything here is plain markdown + YAML frontmatter. No external services. Grep-friendly. Any agent (Claude, Gemini, Codex) can read and write it with basic file tools.

## Files

- `board.md` — the kanban. Single source of truth for "what is being worked on right now." Updated atomically with every task transition.
- `RELEASE-READINESS.md` — the release gate charter. v0.2 cannot be called a release candidate until this passes or an exception is explicitly recorded.
- `tasks/` — one file per task. All the detail.
- `tasks/_template.md` — copy this when creating a new task.

## Task numbering

Zero-padded to 4 digits. Reserved ranges:

| Range | Area |
|---|---|
| 0001–0009 | Core infrastructure (module registry, shell plumbing, event bus) |
| 0010–0029 | ALOSForge |
| 0030–0049 | ALOSCurrent |
| 0050–0069 | ALOSAtlas |
| 0070–0089 | LSP integration |
| 0090–0099 | Agent bridge / MCP tools |
| 0100–0119 | Rebrand / cleanup |
| 0120–0139 | Docs, RFCs-that-become-tasks |
| 0140+ | Overflow, v0.3 seeding |

Pick the next unused number within the appropriate range.

## Lifecycle

```
Backlog ─▶ Ready ─▶ In Progress ─▶ Review ─▶ Done
                │         │           │
                └─── Blocked ◀────────┘
```

### State transitions (must be atomic)

- **Backlog → Ready:** all blockers resolved; acceptance criteria reviewed; task is pickable by any agent.
- **Ready → In Progress:** an agent picks it up. Update frontmatter `status` AND move the line in `board.md`. One commit.
- **In Progress → Review:** code written, tests passing; PR link added to task file.
- **Review → Done:** PR merged; post-merge sanity check passing.
- **Any → Blocked:** add `blocked_by` in frontmatter; move on `board.md`; write why in the task file's "Status updates" section.

## Rules

1. **One task per file.** Never merge tasks. Split if it grows beyond ~1 day of work.
2. **Acceptance criteria must be mechanically verifiable** — file exists, test passes, grep returns zero, UI element renders. No "looks right."
3. **If the task scope changes mid-work,** stop, update the task file (body + acceptance), commit the doc change, then continue coding. Never silently expand scope.
4. **If you find adjacent work,** file a new task. Do not tack it onto yours.
5. **Update `board.md` and the task file in the same commit** as the state change. Drift between them is the #1 failure mode of markdown task systems.
6. **Don't assign agents.** Any agent that reads the task and meets the acceptance criteria can complete it. Self-assignment via `status: in_progress` + `assigned_to: <handle>` is fine; pre-assignment is not.
7. **Don't delete closed tasks.** They're history. Move them to `tasks/_done/` only if the directory gets unwieldy (post-v0.2).

## Frontmatter reference

Every task file starts with:

```yaml
---
id: NNNN
title: Short imperative title
area: forge | current | atlas | lsp | agents | core | rebrand | docs
status: backlog | ready | in_progress | review | done | blocked
assigned_to: null | <handle>
created: YYYY-MM-DD
updated: YYYY-MM-DD
effort: xs | s | m | l            # xs<1h, s<4h, m<1d, l<3d
blocks: [NNNN, ...]               # tasks that can't start until this is done
blocked_by: [NNNN, ...]
related_rfc: null | NNNN
pr: null | <url>
---
```

## Conflict resolution

Two agents pick up the same task → first commit wins. The second agent, on encountering the conflict, moves their edits into a new task or joins the first as a pair.

To minimize this: always `git pull` (or equivalent) before transitioning Ready → In Progress, and make the state-change commit first before any code.
