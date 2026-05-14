# ALOSCortex — Future Module (not in v0.2)

**Canonical name:** ALOSCortex  
**Dead name:** AI Model Lab  
**Source:** `Upgrades From Rex/ai-model-lab/` *(or `/Volumes/DDrive/Rex'S Upgrades/ai-model-lab/`)*  
**Target location:** `modules/cortex/` *(reserved, not created in v0.2)*  
**Tagline:** "Train, fine-tune, and swap models without leaving your IDE."

## Purpose

Model management surface for ALOS. Local model registry, fine-tuning jobs, evaluation harness, model switch per-agent.

## Why it matters

Long-term ALOS differentiation: every module runs against models the user owns or controls. Cortex is the control room for that. It also underpins the eventual BitNet story (deferred separately).

## Reserved surface

- **Route:** `/cortex`
- **Activity bar order:** 40 (reserved, hidden in v0.2)
- **Python package name:** `alos_cortex`
- **Events namespace:** `cortex.*`
- **MCP tools prefix:** `cortex_*`

## v0.2 obligations

- Keep the module id in the activity-bar registry type union (so the type is stable when Cortex lands).
- Do **not** create `modules/cortex/` directory yet (avoids half-built code review confusion).
- Do **not** reserve ports, paths, or DB files yet — all TBD.

## Known source-material traits (for future integration planners)

Evaluate the source when Cortex reaches planning. Expected to contain model registry, training loop harness, and evaluation tooling. No commitment without fresh eval.

## Open questions (resolve before Cortex planning starts)

- Does Cortex ship its own inference endpoint or consume a user-configured one (Ollama, LM Studio, llama.cpp)?
- How does Cortex interact with LangGraph agent configuration (runtime model swap per agent)?
- Training jobs are long. Do they run as Current workflows, or does Cortex have its own job queue?
