# RFCs

**Purpose:** capture architecture decisions with enough rationale that six months from now — or a new agent three minutes from now — can understand *why* we did what we did, not just *what* we did.

## When to write an RFC

Write an RFC if you're about to:

- Change a contract in `*/contracts/` in a way that isn't purely additive.
- Add or remove an event from `src/contracts/events.ts`.
- Add or remove a module.
- Change how modules are discovered, loaded, or isolated.
- Change the agent routing policy (ambiguity epsilon, stickiness bonus, decay rate).
- Change the IPC channels (add a new one, deprecate an existing one).
- Add a new risk-level, capability, or gate.
- Rebrand anything locked in [../00-overview/naming.md](../00-overview/naming.md).
- Change where persistence lives for any module.

## When NOT to write an RFC

Skip it for:

- Pure implementation of a task file's acceptance criteria.
- Bug fixes that don't change contracts.
- Renaming a variable, cleaning up a module's internals, reformatting.
- Adding a test.
- Adding a node type to Current that doesn't require new contracts.

## Process

1. Copy `_template.md` → `NNNN-short-slug.md` (next unused number).
2. Fill in. Be specific. No "we'll figure it out later."
3. Commit as draft (`status: draft` in frontmatter).
4. Flag it in the PR description or chat to the relevant reviewers.
5. Iterate. Land changes.
6. Before merging any code that depends on the RFC: change frontmatter to `status: accepted` and the date.
7. If superseded later, don't delete the old RFC — mark it `status: superseded_by: NNNN` and keep it as history.

## Numbering

Zero-padded to 4 digits. Current next number: **0001**.

## File list

*(populated as RFCs are written — keep this index current)*

- [`0001-module-registry-and-activity-bar.md`](0001-module-registry-and-activity-bar.md) — **accepted 2026-04-15.** Locks the module discovery contract, activity bar behavior, order reservation, icon source, unavailable-module rendering, active-module persistence, and badge contract.
