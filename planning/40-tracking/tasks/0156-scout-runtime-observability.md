# 0156 — Scout Runtime Observability

## Status

Completed.

## Purpose

Restore ALOS Scout as the release-debugging surface so QA can inspect backend logs, frontend renderer failures, shell events, agent run events, and module lifecycle activity in one place before rebuilding packages repeatedly.

## Acceptance Criteria

- Scout is available as a first-class sidebar module.
- Backend logs are persisted as structured Scout events.
- Agent run events are mirrored into Scout with run/session ids.
- Frontend console warnings/errors, window errors, unhandled rejections, and shell event-bus traffic are captured.
- Scout can load recent history and stream new events live.
- ALOS agents can query Scout through a read-only tool.
- Secrets and API keys are redacted before events are stored.
- Scout failures must not break normal app behavior.

## Notes

- Scout is for release diagnostics and support. It is intentionally separate from the module event bus, which remains a non-persistent coordination channel.
- The v0.2 implementation keeps the stream local-only and authenticated through the existing API key flow.
- Verification passed: backend unit/eval suite, frontend TypeScript build, production frontend build, and Rust `cargo check`.
- Fresh GitNexus impact after re-index: `scout_query` and `ScoutView` are low risk; `emit_scout_event` is central/critical by design and should be treated as release-sensitive.
