export type NodeStatus = 'idle' | 'running' | 'succeeded' | 'failed' | 'paused' | 'skipped';
export type WorkflowStatus = 'draft' | 'published' | 'archived';
export type ExecutionStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type FieldType = 'string' | 'text' | 'number' | 'boolean' | 'select' | 'secret' | 'agent_select';

export interface XYPosition {
  x: number;
  y: number;
}

export interface ConfigField {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  default?: string | number | boolean;
  options?: string[];
}

export interface NodePort {
  id: string;
  label: string;
}

export interface NodeType {
  type: string;
  label: string;
  category: string;
  icon: string;
  description: string;
  executor: string;
  inputs: NodePort[];
  outputs: NodePort[];
  configSchema: ConfigField[];
}

export interface WorkflowNode {
  id: string;
  type: string;
  name: string;
  position: XYPosition;
  config: Record<string, string | number | boolean | null>;
  status: NodeStatus;
}

export interface WorkflowEdge {
  id: string;
  sourceNodeId: string;
  sourcePort: string;
  targetNodeId: string;
  targetPort: string;
}

export interface WorkflowGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  variables: Record<string, unknown>;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string;
  status: WorkflowStatus;
  activeVersionId: string | null;
  draft: WorkflowGraph;
  metadata: {
    createdAt: string;
    updatedAt: string;
    createdBy: string;
    tags: string[];
  };
  settings: {
    timeout: number;
    retries: number;
    concurrencyLimit: number;
  };
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  graph: WorkflowGraph;
  created_at: string;
  created_by: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  order: string[];
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  version_id: string;
  status: ExecutionStatus;
  current_node_id: string | null;
  variables: Record<string, unknown>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

export interface ExecutionStep {
  id: string;
  execution_id: string;
  node_id: string;
  status: string;
  attempt: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface AlosCurrentEvent {
  id: string;
  type: string;
  workflow_id?: string | null;
  execution_id?: string | null;
  node_id?: string | null;
  level: 'info' | 'warn' | 'error';
  message: string;
  payload: Record<string, unknown>;
  delivery_status: string;
  timestamp: string;
}

export interface WorkflowTask {
  id: string;
  workflow_id?: string | null;
  execution_id?: string | null;
  node_id?: string | null;
  title: string;
  description: string;
  department_id?: string | null;
  assignee_id?: string | null;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  status: 'backlog' | 'ready' | 'in_progress' | 'review' | 'blocked' | 'done' | 'cancelled';
  acceptance_criteria: string;
  due_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  name: string;
  head_id: string;
  authority_tier: number;
  capabilities: string[];
}

export interface Agent {
  id: string;
  name: string;
  kind: 'department_head' | 'sub_agent' | 'human';
  department_id: string;
  capabilities: string[];
  available: number;
}
