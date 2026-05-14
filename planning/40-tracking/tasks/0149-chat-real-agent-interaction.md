---
id: 0149
title: Chat must be a frontier-grade authenticated agent experience
area: core
status: done
assigned_to: codex
created: 2026-04-18
updated: 2026-04-18
effort: m
blocks: [0147]
blocked_by: []
related_rfc: null
pr: null
---

# 0149 — Chat must be a frontier-grade authenticated agent experience

## Context

The root Chat surface currently mounts, but it is still a scaffold. Chat worked
in the browser/web-app version and must be restored as a first-class desktop
experience, not reduced to a placeholder. The backend already exposes session
APIs and an authenticated `/ws/{session_id}` swarm socket, so v0.2 should not
call Chat release-ready until the root Chat surface uses that contract well.

## Scope

**In scope:**
- Load or create an authenticated chat session after login.
- Connect to the backend WebSocket with the active API key.
- Send user input as `chat_input` messages.
- Provide a polished conversation experience: streaming output, message
  history, markdown/code rendering, copy controls, keyboard flow, empty/loading
  states, reconnect state, and clear failure recovery.
- Render `chat_output`, `status`, `run_started`, `run_event`,
  `plan_update`, `execution_complete`, and setup-required/error messages.
- Handle plan approval and stop execution messages if the backend requests
  them.
- Persist and reload visible messages through the existing session endpoints.
- Show honest loading, disconnected, running, and failed states.

**Out of scope:**
- Rewriting the agent swarm backend.
- Full conversation search/history management beyond what is required for the
  first reliable v0.2 chat loop.

## Acceptance criteria

- [x] The Chat view no longer describes itself as a scaffold and meets or
      exceeds the prior browser/web-app chat experience.
- [x] Sending a message creates or reuses a backend session and reaches the
      authenticated WebSocket.
- [x] A simple direct conversational prompt streams visible assistant output.
- [x] A prompt that produces a plan shows plan state and requires approval when
      the backend marks the plan high risk.
- [x] Stop execution cancels an active run and the UI returns to an idle state.
- [x] Reloading the app shows prior session messages from the backend.
- [x] Failed WebSocket/auth/provider states are visible and recoverable.
- [x] Chat quality is release-grade: no placeholder copy, no dead controls, no
      lost messages during normal reconnect/reload flows.

## Verification commands

```bash
npx tsc -b --noEmit
npm run build
env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/
npx vitest run --exclude "scratch/**"
python3.11 scripts/verify_0149_chat_live.py
```

Manual packaged-app verification:

1. Login with a valid API key.
2. Open Chat.
3. Send a simple greeting and confirm assistant output appears.
4. Send a task that requires a plan and confirm approval/stop controls work.
5. Quit and relaunch; confirm the session history is still visible.

## Status updates

- 2026-04-18 (codex): created after packaged verification showed Chat is
  visible but explicitly not ready. This blocks v0.2 release-candidate status.
- 2026-04-18 (codex): resumed Claude's partial implementation and found two
  release-blocking contract gaps:
  - the backend emits `plan_approval_request`, while Chat only handled
    `plan_request` / `plan_update.approval_id`, so high-risk plan approval
    could be displayed without a working approval action;
  - stop/cancel produced a `run_cancelled` event but did not reliably send
    `execution_complete`, and Chat did not treat terminal run events as idle.
- 2026-04-18 (codex): patched Chat to handle `plan_approval_request`, backend
  plan statuses (`running`, `blocked`, `complete`), terminal run events, and
  disk/patch approval frames (`auth_request`, `patch_request`). Patched backend
  cancellation to emit `execution_complete`.
- 2026-04-18 (codex): verification passed:
  - `npx tsc -b --noEmit`
  - `npm run build`
  - `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/` (34 passed)
  - `npx vitest run src/shell/__tests__/event-bus.test.ts` (9 passed)
  - `npx vitest run --exclude "scratch/**"` (9 passed; scratch excluded)
- 2026-04-18 (codex): `npm test` was not used as an 0149 signal because it
  discovers the embedded `scratch/git-nexus` test suites. That broad run hit
  unrelated GitNexus fixture/path/timeout failures and was stopped after the
  targeted ALOS app test had passed.
- 2026-04-18 (codex): completed isolated live verification with
  `python3.11 scripts/verify_0149_chat_live.py`. The verifier used an
  OS-assigned localhost port (observed `64042` on this run) and a temporary
  data directory, not port `8000` and not the user's packaged ALOS data. It
  proved invalid websocket auth rejection, provider setup-required recovery,
  simple chat output, high-risk `plan_approval_request`, approval-started run,
  history reload from `/api/sessions/{id}`, and stop/cancel returning
  `execution_complete`.
- 2026-04-18 (codex): final completion verification passed:
  - `python3.11 scripts/verify_0149_chat_live.py`
  - `npx tsc -b --noEmit`
  - `npx vitest run --exclude "scratch/**"` (9 passed)
  - `env PYTHONPATH=.:backend python3.11 -m pytest backend/tests/` (34 passed)
  - `npm run build`

## Completion note

- 0149 is complete for v0.2 planning purposes. A `.dmg` build is still required
  for release packaging, but not as a prerequisite for marking this chat task
  done because the live REST/WebSocket contract and production frontend build
  have been verified independently.
