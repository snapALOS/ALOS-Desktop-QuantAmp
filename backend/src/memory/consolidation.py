from collections import Counter
import re
from typing import Any, Dict, List, Optional

from src.api.database import list_strategic_memories, record_strategic_memory
from src.memory.schema import StrategicMemory, redact_secrets


PREFERENCE_PATTERNS = [
    re.compile(r"(?i)\b(?:i prefer|i want|remember that|always|never|do not|don't)\b.{0,240}"),
]

DECISION_PATTERNS = [
    re.compile(r"(?i)\b(?:decided|approved|rejected|chosen|we will|we should|must keep|stays?|do only phase)\b.{0,260}"),
]

FACT_PATTERNS = [
    re.compile(r"(?i)\b(?:alos|memory|launcher|port|phase|ui|api|database|vector_store|server\.py)\b.{0,220}"),
]

INTEGRATION_PATTERNS = [
    re.compile(r"(?i)\b(?:integration|plugin|provider|openclaw|api|external|future)\b.{0,220}"),
]

STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will", "into", "should",
    "would", "there", "their", "about", "after", "before", "node", "agent", "memory",
}


def _content_from_message(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content") or message.get("data", {}).get("content")
    return str(content or "").strip()


def _message_type(message: Any) -> str:
    msg_type = getattr(message, "type", None)
    if msg_type is None and isinstance(message, dict):
        msg_type = message.get("type", "")
    return str(msg_type or "")


def _make_memory(
    *,
    session_id: str,
    memory_type: str,
    content: str,
    importance: float,
    source: str,
    confidence: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[StrategicMemory]:
    content, _ = redact_secrets(content)
    if not content.strip():
        return None
    memory = StrategicMemory(
        session_id=session_id,
        memory_type=memory_type,
        content=content.strip(),
        importance=importance,
        source=source,
        confidence=confidence,
        metadata=metadata or {},
    ).sanitized()
    record_strategic_memory(memory.public_dict())
    return memory


def promote_checkpoint(state_snapshot: Dict[str, Any], triggering_node: str, session_id: str) -> List[StrategicMemory]:
    promoted: List[StrategicMemory] = []
    messages = state_snapshot.get("messages") or []
    latest = messages[-1] if isinstance(messages, list) and messages else None
    latest_content = _content_from_message(latest)
    latest_type = _message_type(latest)
    source = triggering_node or state_snapshot.get("active_worker") or "graph"

    errors = [str(error) for error in state_snapshot.get("error_history", []) if str(error).strip()]
    if errors:
        memory = _make_memory(
            session_id=session_id,
            memory_type="failure_pattern",
            content=f"Failure pattern at {source}: {' | '.join(errors[-3:])}",
            importance=0.92,
            source=source,
            confidence=0.88,
            metadata={"active_step": state_snapshot.get("current_step_id", ""), "promotion": "error_history"},
        )
        if memory:
            promoted.append(memory)

    if latest_type == "tool" and latest_content:
        memory = _make_memory(
            session_id=session_id,
            memory_type="tool_result",
            content=f"Tool result from {source}: {latest_content[:1200]}",
            importance=0.72,
            source=source,
            confidence=0.82,
            metadata={"active_step": state_snapshot.get("current_step_id", ""), "promotion": "tool_message"},
        )
        if memory:
            promoted.append(memory)

    if latest_content:
        for pattern in PREFERENCE_PATTERNS:
            match = pattern.search(latest_content)
            if match:
                memory = _make_memory(
                    session_id=session_id,
                    memory_type="user_preference",
                    content=f"User preference: {match.group(0).strip()}",
                    importance=0.95,
                    source=source,
                    confidence=0.86,
                    metadata={"promotion": "preference_pattern"},
                )
                if memory:
                    promoted.append(memory)
                break

        for pattern in DECISION_PATTERNS:
            match = pattern.search(latest_content)
            if match:
                memory = _make_memory(
                    session_id=session_id,
                    memory_type="decision",
                    content=f"Decision: {match.group(0).strip()}",
                    importance=0.86,
                    source=source,
                    confidence=0.78,
                    metadata={"promotion": "decision_pattern"},
                )
                if memory:
                    promoted.append(memory)
                break

        if latest_type == "ai":
            memory = _make_memory(
                session_id=session_id,
                memory_type="execution_insight",
                content=f"Execution insight from {source}: {latest_content[:1200]}",
                importance=0.64,
                source=source,
                confidence=0.72,
                metadata={"promotion": "agent_message"},
            )
            if memory:
                promoted.append(memory)

        for pattern in FACT_PATTERNS:
            match = pattern.search(latest_content)
            if match:
                memory = _make_memory(
                    session_id=session_id,
                    memory_type="project_fact",
                    content=f"Project fact: {match.group(0).strip()}",
                    importance=0.74,
                    source=source,
                    confidence=0.68,
                    metadata={"promotion": "project_fact_pattern"},
                )
                if memory:
                    promoted.append(memory)
                break

        for pattern in INTEGRATION_PATTERNS:
            match = pattern.search(latest_content)
            if match:
                memory = _make_memory(
                    session_id=session_id,
                    memory_type="integration_note",
                    content=f"Integration note: {match.group(0).strip()}",
                    importance=0.70,
                    source=source,
                    confidence=0.66,
                    metadata={"promotion": "integration_pattern"},
                )
                if memory:
                    promoted.append(memory)
                break

    return promoted


def consolidate_session_memories(session_id: str) -> Dict[str, Any]:
    memories = list_strategic_memories(session_id=session_id, include_checkpoints=True, limit=1000)
    if not memories:
        return {"total_memories": 0, "promoted": 0, "summary": "No memories to consolidate."}

    strategic = [item for item in memories if item.get("memory_type") != "checkpoint"]
    text = " ".join(item.get("content", "") for item in strategic or memories)
    words = [
        word
        for word in re.findall(r"[a-z0-9_./:-]+", text.lower())
        if len(word) > 3 and word not in STOP_WORDS
    ]
    themes = [word for word, _count in Counter(words).most_common(8)]
    by_type = Counter(item.get("memory_type", "execution_insight") for item in memories)
    summary = (
        f"Run memory summary: {len(memories)} memories, "
        f"{len(strategic)} strategic memories, key themes: {', '.join(themes[:5]) or 'none'}."
    )
    summary_memory = _make_memory(
        session_id=session_id,
        memory_type="run_summary",
        content=summary,
        importance=0.82,
        source="memory_consolidation",
        confidence=0.80,
        metadata={"themes": themes, "type_counts": dict(by_type)},
    )
    return {
        "total_memories": len(memories),
        "strategic_memories": len(strategic),
        "summary": summary,
        "key_themes": themes,
        "type_counts": dict(by_type),
        "promoted": 1 if summary_memory else 0,
    }
