# ALOSReflex — Future Module (not in v0.2)

**Canonical name:** ALOSReflex  
**Dead name:** Scenario Toolkit  
**Source:** `Upgrades From Rex/scenario-toolkit/` *(or `/Volumes/DDrive/Rex'S Upgrades/scenario-toolkit/`)*  
**Target location:** `modules/reflex/` *(reserved, not created in v0.2)*  
**Tagline:** "Agent behavior under pressure. Scenarios, red-teaming, regressions."

## Purpose

A scenario runner for agents. Scripted situations (success path, edge cases, adversarial inputs, regressions) replayed against the agent fleet to measure behavior, catch regressions, and validate capability gates.

## Why it matters

Agents drift. New prompts, new tools, new models — any of these can silently break what used to work. Reflex is the agentic-equivalent of a test suite, but at the behavior layer rather than the code layer.

It also provides the red-team substrate ALOS will market toward enterprise users: "prove your agents do not exfiltrate secrets / refuse correctly / escalate safely."

## Reserved surface

- **Route:** `/reflex`
- **Activity bar order:** 50 (reserved, hidden in v0.2)
- **Python package name:** `alos_reflex`
- **Events namespace:** `reflex.*`
- **MCP tools prefix:** `reflex_*`

## v0.2 obligations

- Keep module id in type union.
- Do not create directory.

## Open questions (for future planners)

- Scenarios as YAML/JSON/code? How expressive?
- Reflex runs scenarios — does it reuse Current as its runtime, or does it have its own?
- How are scenarios versioned alongside agent configs?
- What is the scoring model (pass/fail, rubric, LLM judge)?
