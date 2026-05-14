/**
 * Forge module — event contract (stub).
 *
 * Forge is the agentic IDE. v0.2 ships without outbound events — Forge
 * consumes core filesystem + terminal commands but does not yet publish
 * module-scoped events on the bus. This file exists so MODULE.toml's
 * contracts.events path resolves and future events (file-opened, agent-run
 * started/completed, diff-accepted) land here rather than in the module's
 * private surface.
 *
 * When adding an event:
 *   1. Define the payload as an interface below.
 *   2. Add a discriminated-union member to `ForgeEvent`.
 *   3. Re-export via `@/contracts/events` so the global bus knows about it.
 */

export {}
