# Chamber Pre-write Gates

Chamber is the write safety layer for ALOS v0.2 agent work. Agents may propose
patches, but the workspace write is blocked until Chamber stages the proposed
content, runs validation commands, records evidence, and hands the result back
to the mutation gate.

## Lifecycle

1. Agent proposes a patch through `propose_patch` or `/api/patches/propose`.
2. A patch proposal and mutation proposal are created, but no disk write occurs.
3. Chamber creates a `staged` gate record for the patch.
4. When the patch is applied, Chamber copies the workspace into an isolated
   run directory, overlays the proposed content, and runs inferred commands.
5. If every command passes, the mutation gate writes to disk and Chamber records
   the gate as `written`.
6. If a command fails, Chamber records evidence, marks the patch `blocked`, and
   leaves the workspace untouched.
7. A user override can apply a blocked patch only through an explicit
   `override_chamber=true` apply request, which records the approving actor.

## Statuses

- `staged`: patch exists and is waiting for validation.
- `running`: Chamber is preparing an isolated workspace or running commands.
- `passed`: all validation commands passed and the patch is eligible to write.
- `failed`: validation did not pass.
- `blocked`: failed validation blocked the workspace write.
- `written`: validation passed and the mutation gate wrote the file.
- `overridden`: a user explicitly bypassed failed validation.

## Command Selection

Chamber infers commands from the staged file:

- TypeScript, JavaScript, JSON, CSS, and HTML run `npx tsc -b --noEmit`.
- Python and backend files run `python3.11 -m pytest tests`.
- Documentation files run a lightweight documentation gate.
- High-risk unknown files fall back to backend tests.

The command evidence is stored with each gate and exposed through
`/api/chamber/gates`.

## Agent Integration

Forge and Current agents are instructed not to write directly. They route file
changes through patch proposals, and patch application now always enters the
Chamber gate before the mutation manager can execute the write. The same gate
protects autonomous Chat agent work because all registered write tools use the
same `src.tools.patching` path.
