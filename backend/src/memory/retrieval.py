import re
from typing import Dict, List, Optional

from src.api.database import list_strategic_memories
from src.memory.schema import MemorySearchRequest, MemorySearchResult, StrategicMemory, normalize_memory_type
from src.memory.quant_amp import QuantAmpAtomizer, QIP, QuantumCollapse


TASK_TYPE_POLICY: Dict[str, List[str]] = {
    "coding": ["decision", "project_fact", "failure_pattern", "tool_result", "execution_insight", "user_preference"],
    "debugging": ["failure_pattern", "tool_result", "execution_insight", "decision", "project_fact"],
    "planning": ["decision", "project_fact", "run_summary", "integration_note", "user_preference"],
    "setup": ["project_fact", "failure_pattern", "decision", "integration_note"],
    "memory": ["user_preference", "project_fact", "decision", "run_summary", "execution_insight"],
}

SCOPE_POLICY: Dict[str, Dict[str, object]] = {
    "matters": {
        "include_checkpoints": False,
        "boosts": {
            "user_preference": 0.35,
            "decision": 0.30,
            "project_fact": 0.25,
            "failure_pattern": 0.25,
            "integration_note": 0.20,
            "run_summary": 0.18,
        },
    },
    "happened": {
        "include_checkpoints": True,
        "boosts": {
            "checkpoint": 0.46,
            "tool_result": 0.24,
            "run_summary": 0.18,
            "execution_insight": 0.14,
        },
    },
    "all": {
        "include_checkpoints": True,
        "boosts": {},
    },
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_./:-]+", (text or "").lower())
        if len(token) > 2
    }


def _memory_from_payload(payload: dict) -> StrategicMemory:
    if hasattr(StrategicMemory, "model_validate"):
        return StrategicMemory.model_validate(payload)
    return StrategicMemory.parse_obj(payload)


def infer_task_type(query: str) -> str:
    text = (query or "").lower()
    if any(word in text for word in ["debug", "failure", "failed", "error", "regression"]):
        return "debugging"
    if any(word in text for word in ["code", "file", "patch", "implement", "backend", "frontend"]):
        return "coding"
    if any(word in text for word in ["plan", "roadmap", "phase", "decision"]):
        return "planning"
    if any(word in text for word in ["setup", "install", "provider", "port"]):
        return "setup"
    if any(word in text for word in ["prefer", "preference", "remember", "memory"]):
        return "memory"
    return "coding"


def search_memory(
    query: str,
    *,
    session_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    scope: str = "matters",
    task_type: Optional[str] = None,
    limit: int = 10,
) -> List[MemorySearchResult]:
    request = MemorySearchRequest(
        query=query or "",
        session_id=session_id or None,
        memory_type=normalize_memory_type(memory_type) if memory_type else None,
        scope=scope if scope in SCOPE_POLICY else "matters",
        task_type=task_type or infer_task_type(query),
        limit=limit,
    )
    policy = SCOPE_POLICY[request.scope]
    include_checkpoints = bool(policy["include_checkpoints"])
    task_memory_types = TASK_TYPE_POLICY.get(request.task_type or "", [])
    query_tokens = _tokens(request.query)

    # [QUANTAMP INTEGRATION]
    # Generate query signature for Resonance check if query exists
    query_sig = None
    if request.query:
        query_atom = QuantAmpAtomizer.atomize(request.query)
        query_pulse = QIP.synthesize_pulse(query_atom)
        query_sig = QuantumCollapse.encode(query_pulse)

    rows = list_strategic_memories(
        session_id=request.session_id,
        memory_type=request.memory_type,
        include_checkpoints=include_checkpoints,
        limit=max(request.limit * 8, 80),
    )

    results: List[MemorySearchResult] = []
    for row in rows:
        memory = _memory_from_payload(row)
        content_tokens = _tokens(memory.content)
        metadata_text = " ".join(str(value) for value in memory.metadata.values())
        metadata_tokens = _tokens(metadata_text)
        overlap = len(query_tokens & (content_tokens | metadata_tokens))
        lexical_score = overlap / max(len(query_tokens), 1)
        exact_bonus = 0.25 if request.query and request.query.lower() in memory.content.lower() else 0.0
        importance_score = memory.importance * 0.35
        confidence_score = memory.confidence * 0.15
        scope_boosts = policy.get("boosts", {})
        type_boost = float(scope_boosts.get(memory.memory_type, 0.0)) if isinstance(scope_boosts, dict) else 0.0
        task_boost = 0.16 if memory.memory_type in task_memory_types else 0.0
        checkpoint_penalty = -0.08 if memory.memory_type == "checkpoint" and request.scope != "happened" else 0.0
        
        # [QUANTAMP INTEGRATION]
        # Calculate Hamming Resonance boost
        resonance_boost = 0.0
        if query_sig:
            stored_sig_hex = memory.metadata.get("q_signature")
            if stored_sig_hex:
                try:
                    stored_sig = bytes.fromhex(stored_sig_hex)
                    hamming = QuantumCollapse.hamming_distance(query_sig, stored_sig)
                    # Normalize resonance (lower Hamming -> higher resonance)
                    resonance = 1.0 - (hamming / 1024.0)
                    resonance_boost = resonance * 0.25 # Max boost of 0.25
                except Exception:
                    pass

        score = lexical_score + exact_bonus + importance_score + confidence_score + type_boost + task_boost + checkpoint_penalty + resonance_boost
        if request.query and overlap == 0 and exact_bonus == 0 and memory.memory_type not in task_memory_types:
            score *= 0.35
        reason = f"{request.scope}:{memory.memory_type}"
        results.append(MemorySearchResult(memory=memory, score=round(score, 4), reason=reason))

    results.sort(key=lambda item: (item.score, item.memory.importance, item.memory.created_at), reverse=True)
    return results[: request.limit]


def public_search(
    query: str,
    *,
    session_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    scope: str = "matters",
    task_type: Optional[str] = None,
    limit: int = 10,
) -> dict:
    results = search_memory(
        query,
        session_id=session_id,
        memory_type=memory_type,
        scope=scope,
        task_type=task_type,
        limit=limit,
    )
    return {
        "query": query or "",
        "scope": scope if scope in SCOPE_POLICY else "matters",
        "task_type": task_type or infer_task_type(query),
        "memories": [result.public_dict() for result in results],
    }
