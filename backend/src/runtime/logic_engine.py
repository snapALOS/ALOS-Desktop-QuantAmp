from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain_core.messages import AIMessage


MAX_ENGINE_CYCLES = 80
MAX_REPEATED_SIGNATURES = 6
MAX_CONTEXT_CHARS = 12000


class LogicEngineStuck(RuntimeError):
    """Raised when a run repeats work or exceeds bounded orchestration limits."""

    def __init__(self, reason: str, *, trace: list[dict[str, Any]] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.trace = trace or []


def normalize_module_context(value: Any) -> dict[str, Any]:
    """Return bounded, JSON-safe module context for injection into run state."""
    if not isinstance(value, dict):
        return {}

    module_id = str(value.get("module_id") or value.get("moduleId") or "unknown")[:80]
    module_name = str(value.get("module_name") or value.get("moduleName") or module_id)[:120]
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    text = json.dumps(payload, default=str, sort_keys=True)
    if len(text) > MAX_CONTEXT_CHARS:
        payload = {
            "truncated": True,
            "original_chars": len(text),
            "preview": text[:MAX_CONTEXT_CHARS],
        }

    return {
        "module_id": module_id,
        "module_name": module_name,
        "captured_at": str(value.get("captured_at") or value.get("capturedAt") or ""),
        "payload": payload,
    }


def context_directive(module_context: dict[str, Any] | None) -> str:
    context = normalize_module_context(module_context)
    if not context:
        return ""
    return (
        "\n\nACTIVE MODULE CONTEXT:\n"
        f"{json.dumps(context, default=str, sort_keys=True, indent=2)}\n"
        "Use this context as evidence about the user's current ALOS module. "
        "Do not invent missing state; ask for clarification when the context is insufficient."
    )


def tool_idempotency_key(run_id: str, tool_name: str, tool_id: str, tool_args: Any) -> str:
    payload = json.dumps(tool_args or {}, default=str, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{run_id}:{tool_name}:{tool_id}:{digest}"


def _tool_signature(message: Any) -> str:
    calls = getattr(message, "tool_calls", None) or []
    if not calls:
        return ""
    parts = []
    for call in calls:
        name = str(call.get("name") or "")
        args = json.dumps(call.get("args") or {}, default=str, sort_keys=True)
        parts.append(f"{name}:{hashlib.sha256(args.encode('utf-8')).hexdigest()[:12]}")
    return "|".join(parts)


def node_signature(node_name: str, node_state: dict[str, Any]) -> str:
    worker = str(node_state.get("active_worker") or "")
    messages = node_state.get("messages") or []
    latest = messages[-1] if isinstance(messages, list) and messages else messages
    tool_sig = _tool_signature(latest)
    content_sig = ""
    if isinstance(latest, AIMessage) and not tool_sig:
        content = str(getattr(latest, "content", "") or "")
        content_sig = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"{node_name}:{worker}:{tool_sig}:{content_sig}"


def record_engine_step(
    session_state: dict[str, Any],
    node_name: str,
    node_state: dict[str, Any],
    *,
    max_cycles: int = MAX_ENGINE_CYCLES,
    max_repeats: int = MAX_REPEATED_SIGNATURES,
) -> dict[str, Any]:
    trace = list(session_state.get("logic_trace") or [])
    signature = node_signature(node_name, node_state)
    trace.append({
        "node": node_name,
        "active_worker": node_state.get("active_worker") or session_state.get("active_worker") or "",
        "signature": signature,
    })
    trace = trace[-max_cycles:]
    session_state["logic_trace"] = trace
    session_state["logic_cycle_count"] = int(session_state.get("logic_cycle_count") or 0) + 1

    if session_state["logic_cycle_count"] > max_cycles:
        raise LogicEngineStuck(
            f"Run exceeded the bounded orchestration limit of {max_cycles} cycles.",
            trace=trace,
        )

    repeat_count = sum(1 for item in trace[-max_repeats:] if item.get("signature") == signature)
    if signature and repeat_count >= max_repeats:
        raise LogicEngineStuck(
            f"Run repeated the same route/action signature {repeat_count} times.",
            trace=trace,
        )

    return {"cycle_count": session_state["logic_cycle_count"], "signature": signature}
