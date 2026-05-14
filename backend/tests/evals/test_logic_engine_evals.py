from __future__ import annotations

from src.planning.planner import create_run_plan
from src.runtime.logic_engine import normalize_module_context


EVAL_CASES = [
    {
        "name": "forge_coding_help",
        "prompt": "In Forge, implement a backend websocket fix and verify it.",
        "surface": "Forge IDE",
        "must_require_verification": True,
    },
    {
        "name": "current_workflow_design",
        "prompt": "In Current, design a workflow with agent review and manual approval.",
        "surface": "Current workflow orchestration",
        "must_require_verification": True,
    },
    {
        "name": "atlas_impact_analysis",
        "prompt": "Use Atlas to analyze dependency impact before editing the chat module.",
        "surface": "Atlas dependency intelligence",
        "must_require_verification": True,
    },
    {
        "name": "chamber_gated_patch",
        "prompt": "Modify a backend file and write only after Chamber passes.",
        "surface": "Chamber write gate",
        "must_require_verification": True,
    },
]


def test_logic_engine_eval_cases_have_evidence_surface_and_verification():
    for case in EVAL_CASES:
        plan = create_run_plan(case["prompt"])
        data = plan.model_dump()
        assert case["surface"] in data["affected_surfaces"], case["name"]
        assert data["evidence_requirements"], case["name"]
        assert data["verification_required"] is case["must_require_verification"], case["name"]


def test_context_eval_payload_is_sanitized_shape():
    context = normalize_module_context({
        "module_id": "current",
        "module_name": "Current",
        "payload": {"workflow": {"nodes": [{"id": "a"}], "edges": []}},
    })

    assert context["module_id"] == "current"
    assert context["payload"]["workflow"]["nodes"][0]["id"] == "a"
