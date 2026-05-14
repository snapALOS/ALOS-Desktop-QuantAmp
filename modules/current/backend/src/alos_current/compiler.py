from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .nodes import NODE_BY_TYPE


class ValidationError(Exception):
    pass


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    errors: list[str] = []
    warnings: list[str] = []
    node_by_id = {node.get("id"): node for node in nodes if node.get("id")}

    if not nodes:
        errors.append("workflow must contain at least one node")
    if len(node_by_id) != len(nodes):
        errors.append("node ids must be unique and non-empty")

    triggers = [node for node in nodes if NODE_BY_TYPE.get(node.get("type"), {}).get("category") == "trigger"]
    if not triggers:
        errors.append("workflow requires at least one trigger node")

    for node in nodes:
        node_type = node.get("type")
        spec = NODE_BY_TYPE.get(node_type)
        if not spec:
            errors.append(f"unknown node type: {node_type}")
            continue
        config = node.get("config") or {}
        for field in spec.get("configSchema", []):
            if field.get("required") and _missing(config.get(field["key"])):
                errors.append(f"{node.get('name') or node.get('id')} missing required config `{field['key']}`")

    for edge in edges:
        source = node_by_id.get(edge.get("sourceNodeId"))
        target = node_by_id.get(edge.get("targetNodeId"))
        if not source:
            errors.append(f"edge {edge.get('id')} has missing source node")
            continue
        if not target:
            errors.append(f"edge {edge.get('id')} has missing target node")
            continue
        source_ports = {port["id"] for port in NODE_BY_TYPE[source["type"]].get("outputs", [])}
        target_ports = {port["id"] for port in NODE_BY_TYPE[target["type"]].get("inputs", [])}
        if edge.get("sourcePort") not in source_ports:
            errors.append(f"edge {edge.get('id')} uses invalid source port")
        if edge.get("targetPort") not in target_ports:
            errors.append(f"edge {edge.get('id')} uses invalid target port")

    order, cycle = topological_order(nodes, edges)
    if cycle:
        errors.append("workflow graph contains a cycle")

    reachable = reachable_nodes([node["id"] for node in triggers if node.get("id")], edges)
    for node_id in node_by_id:
        if node_id not in reachable:
            warnings.append(f"node is unreachable: {node_id}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "order": order,
    }


def compile_graph(graph: dict[str, Any]) -> dict[str, Any]:
    validation = validate_graph(graph)
    if not validation["valid"]:
        raise ValidationError("; ".join(validation["errors"]))
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        outgoing[edge["sourceNodeId"]].append(edge)
        incoming[edge["targetNodeId"]].append(edge)
    return {
        "validation": validation,
        "nodes": nodes,
        "outgoing": dict(outgoing),
        "incoming": dict(incoming),
        "order": validation["order"],
    }


def topological_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[str], bool]:
    node_ids = [node["id"] for node in nodes if node.get("id")]
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = edge.get("sourceNodeId")
        target = edge.get("targetNodeId")
        if source in indegree and target in indegree:
            outgoing[source].append(target)
            indegree[target] += 1
    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return order, len(order) != len(indegree)


def reachable_nodes(start_ids: list[str], edges: list[dict[str, Any]]) -> set[str]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.get("sourceNodeId")].append(edge.get("targetNodeId"))
    seen: set[str] = set()
    queue = deque(start_ids)
    while queue:
        node_id = queue.popleft()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        queue.extend(outgoing[node_id])
    return seen


def _missing(value: Any) -> bool:
    return value is None or value == ""
