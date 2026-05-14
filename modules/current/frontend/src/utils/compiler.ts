import type { NodeType, ValidationResult, WorkflowEdge, WorkflowGraph, WorkflowNode } from '../types/workflow';

export function validateGraph(graph: WorkflowGraph, nodeTypes: NodeType[]): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const registry = new Map(nodeTypes.map((node) => [node.type, node]));
  const nodeMap = new Map<string, WorkflowNode>();
  for (const node of graph.nodes) {
    if (!node.id || nodeMap.has(node.id)) {
      errors.push('Node ids must be unique and non-empty.');
    }
    nodeMap.set(node.id, node);
    const spec = registry.get(node.type);
    if (!spec) {
      errors.push(`Unknown node type: ${node.type}`);
      continue;
    }
    for (const field of spec.configSchema) {
      if (field.required && isMissing(node.config[field.key])) {
        errors.push(`${node.name} missing required config ${field.key}.`);
      }
    }
  }

  const triggers = graph.nodes.filter((node) => registry.get(node.type)?.category === 'trigger');
  if (triggers.length === 0) errors.push('Workflow needs at least one trigger node.');

  for (const edge of graph.edges) {
    const source = nodeMap.get(edge.sourceNodeId);
    const target = nodeMap.get(edge.targetNodeId);
    if (!source || !target) {
      errors.push(`Edge ${edge.id} references a missing node.`);
      continue;
    }
    const sourcePorts = new Set((registry.get(source.type)?.outputs || []).map((port) => port.id));
    const targetPorts = new Set((registry.get(target.type)?.inputs || []).map((port) => port.id));
    if (!sourcePorts.has(edge.sourcePort)) errors.push(`Edge ${edge.id} has an invalid source port.`);
    if (!targetPorts.has(edge.targetPort)) errors.push(`Edge ${edge.id} has an invalid target port.`);
  }

  const { order, cyclic } = topologicalOrder(graph.nodes, graph.edges);
  if (cyclic) errors.push('Workflow graph contains a cycle.');
  const reachable = reachableNodes(triggers.map((node) => node.id), graph.edges);
  for (const node of graph.nodes) {
    if (!reachable.has(node.id)) warnings.push(`Node is unreachable: ${node.name}`);
  }
  return { valid: errors.length === 0, errors, warnings, order };
}

function topologicalOrder(nodes: WorkflowNode[], edges: WorkflowEdge[]): { order: string[]; cyclic: boolean } {
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    if (!indegree.has(edge.sourceNodeId) || !indegree.has(edge.targetNodeId)) continue;
    outgoing.set(edge.sourceNodeId, [...(outgoing.get(edge.sourceNodeId) || []), edge.targetNodeId]);
    indegree.set(edge.targetNodeId, (indegree.get(edge.targetNodeId) || 0) + 1);
  }
  const queue = [...indegree.entries()].filter(([, degree]) => degree === 0).map(([id]) => id);
  const order: string[] = [];
  while (queue.length) {
    const id = queue.shift() as string;
    order.push(id);
    for (const target of outgoing.get(id) || []) {
      indegree.set(target, (indegree.get(target) || 0) - 1);
      if (indegree.get(target) === 0) queue.push(target);
    }
  }
  return { order, cyclic: order.length !== nodes.length };
}

function reachableNodes(startIds: string[], edges: WorkflowEdge[]): Set<string> {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    outgoing.set(edge.sourceNodeId, [...(outgoing.get(edge.sourceNodeId) || []), edge.targetNodeId]);
  }
  const seen = new Set<string>();
  const queue = [...startIds];
  while (queue.length) {
    const id = queue.shift() as string;
    if (seen.has(id)) continue;
    seen.add(id);
    queue.push(...(outgoing.get(id) || []));
  }
  return seen;
}

function isMissing(value: unknown): boolean {
  return value === undefined || value === null || value === '';
}
