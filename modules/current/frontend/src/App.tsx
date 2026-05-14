import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import WorkflowCanvas from './components/workflow-canvas/WorkflowCanvas';
import { api as alosApi } from '@/api';
import { registerModuleAgentContextProvider } from '@/shell/agent-context';
import type { ChatWsClientFrame, ChatWsServerFrame } from '@/types/api';
import { api, apiBase, eventStreamUrl, storedApiToken } from './utils/api';
import { validateGraph } from './utils/compiler';
import type {
  Agent,
  Department,
  ExecutionStep,
  NodeType,
  AlosCurrentEvent,
  ValidationResult,
  WorkflowDefinition,
  WorkflowExecution,
  WorkflowGraph,
  WorkflowTask,
} from './types/workflow';

type Tab = 'designer' | 'monitor' | 'tasks' | 'swarm' | 'agent' | 'audit' | 'settings';
type AgentMessage = { role: 'user' | 'agent' | 'system'; content: string; ts: number };

const emptyValidation: ValidationResult = { valid: false, errors: ['Workflow not loaded.'], warnings: [], order: [] };

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('designer');
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowDefinition | null>(null);
  const [graph, setGraph] = useState<WorkflowGraph>({ nodes: [], edges: [], variables: {} });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult>(emptyValidation);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<WorkflowExecution | null>(null);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [events, setEvents] = useState<AlosCurrentEvent[]>([]);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  const [agentRequest, setAgentRequest] = useState('');
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentConnection, setAgentConnection] = useState<'idle' | 'connecting' | 'open' | 'error'>('idle');
  const [proposalText, setProposalText] = useState('');
  const [proposalStatus, setProposalStatus] = useState<string | null>(null);
  const [message, setMessage] = useState('Loading AlosCurrent...');
  const undoStack = useRef<WorkflowGraph[]>([]);
  const redoStack = useRef<WorkflowGraph[]>([]);
  const agentSocketRef = useRef<WebSocket | null>(null);
  const selectedExecutionId = selectedExecution?.id;

  const nodeTypeMap = useMemo(() => new Map(nodeTypes.map((node) => [node.type, node])), [nodeTypes]);

  useEffect(() => {
    void boot();
    // Current boots its module-local data once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setValidation(validateGraph(graph, nodeTypes));
  }, [graph, nodeTypes]);

  useEffect(() => {
    if (!selectedExecutionId) return;
    const timer = window.setInterval(() => {
      void loadExecution(selectedExecutionId, false);
      void loadEvents(selectedExecutionId);
      void loadTasks();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [selectedExecutionId]);

  useEffect(() => {
    const source = new EventSource(eventStreamUrl('/api/events/stream', {
      executionId: selectedExecution?.id,
    }));
    source.addEventListener('alos_current', (event) => {
      const nextEvent = JSON.parse((event as MessageEvent).data) as AlosCurrentEvent;
      setEvents((items) => {
        if (items.some((item) => item.id === nextEvent.id)) return items;
        return [nextEvent, ...items].slice(0, 200);
      });
    });
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [selectedExecution?.id]);

  useEffect(() => {
    return () => {
      agentSocketRef.current?.close();
      agentSocketRef.current = null;
    };
  }, []);

  useEffect(() => {
    return registerModuleAgentContextProvider('current', () => ({
      module_id: 'current',
      module_name: 'Current',
      captured_at: new Date().toISOString(),
      payload: currentAgentContext(),
    }));
    // Context provider registration intentionally captures the latest Current state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow, graph, validation, selectedExecution, steps, tasks, events, agents]);

  async function boot() {
    try {
      const health = await api<{ ok: boolean }>('/api/health');
      if (!health.ok) throw new Error('AlosCurrent API health check failed.');
      const nodesPayload = await api<{ nodes: NodeType[] }>('/api/nodes');
      setNodeTypes(nodesPayload.nodes);
      await loadWorkflows(true);
      await loadExecutions();
      await loadTasks();
      await loadSwarm();
      await loadAudit();
      setMessage('AlosCurrent ready.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function loadWorkflows(createIfEmpty = false) {
    const payload = await api<{ workflows: WorkflowDefinition[] }>('/api/workflows');
    if (!payload.workflows.length && createIfEmpty) {
      const created = await api<{ workflow: WorkflowDefinition }>('/api/workflows', {
        method: 'POST',
        body: JSON.stringify({ name: 'AlosCurrent Swarm Approval Workflow' }),
      });
      setWorkflows([created.workflow]);
      selectWorkflow(created.workflow);
      return;
    }
    setWorkflows(payload.workflows);
    if (!workflow && payload.workflows[0]) selectWorkflow(payload.workflows[0]);
  }

  function selectWorkflow(nextWorkflow: WorkflowDefinition) {
    setWorkflow(nextWorkflow);
    setGraph(nextWorkflow.draft);
    undoStack.current = [];
    redoStack.current = [];
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }

  function updateGraph(nextGraph: WorkflowGraph, track = true) {
    if (track) {
      undoStack.current.push(graph);
      redoStack.current = [];
    }
    setGraph(nextGraph);
  }

  async function newWorkflow() {
    const created = await api<{ workflow: WorkflowDefinition }>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify({ name: 'New AlosCurrent Workflow' }),
    });
    setWorkflows((items) => [created.workflow, ...items]);
    selectWorkflow(created.workflow);
    setMessage('Workflow created.');
  }

  async function saveWorkflow() {
    if (!workflow) return;
    const saved = await api<{ workflow: WorkflowDefinition }>(`/api/workflows/${workflow.id}`, {
      method: 'PUT',
      body: JSON.stringify({ ...workflow, draft: graph }),
    });
    setWorkflow(saved.workflow);
    setWorkflows((items) => items.map((item) => (item.id === saved.workflow.id ? saved.workflow : item)));
    setMessage('Workflow saved.');
  }

  async function duplicateWorkflow() {
    if (!workflow) return;
    const duplicated = await api<{ workflow: WorkflowDefinition }>(`/api/workflows/${workflow.id}/duplicate`, { method: 'POST' });
    setWorkflows((items) => [duplicated.workflow, ...items]);
    selectWorkflow(duplicated.workflow);
    setMessage('Workflow duplicated.');
  }

  async function deleteWorkflow() {
    if (!workflow || !window.confirm(`Archive ${workflow.name}?`)) return;
    await api(`/api/workflows/${workflow.id}`, { method: 'DELETE' });
    setWorkflow(null);
    setGraph({ nodes: [], edges: [], variables: {} });
    await loadWorkflows(true);
    setMessage('Workflow archived.');
  }

  async function publishWorkflow() {
    if (!workflow) return;
    await saveWorkflow();
    const published = await api<{ workflow: WorkflowDefinition; validation: ValidationResult }>(`/api/workflows/${workflow.id}/publish`, { method: 'POST' });
    setWorkflow(published.workflow);
    setValidation(published.validation);
    setWorkflows((items) => items.map((item) => (item.id === published.workflow.id ? published.workflow : item)));
    setMessage('Workflow published.');
  }

  async function executeWorkflow() {
    if (!workflow) return;
    await saveWorkflow();
    const result = await api<{ execution: WorkflowExecution; steps: ExecutionStep[] }>(`/api/workflows/${workflow.id}/execute`, {
      method: 'POST',
      body: JSON.stringify({ variables: {}, async: true }),
    });
    setSelectedExecution(result.execution);
    setSteps(result.steps);
    setActiveTab('monitor');
    await loadExecutions();
    await loadEvents(result.execution.id);
    await loadTasks();
    setMessage(`Execution ${result.execution.status}.`);
  }

  async function loadExecutions() {
    const payload = await api<{ executions: WorkflowExecution[] }>('/api/executions');
    setExecutions(payload.executions);
  }

  async function loadExecution(executionId: string, switchTab = true) {
    const payload = await api<{ execution: WorkflowExecution; steps: ExecutionStep[] }>(`/api/executions/${executionId}`);
    setSelectedExecution(payload.execution);
    setSteps(payload.steps);
    if (switchTab) setActiveTab('monitor');
  }

  async function cancelExecution() {
    if (!selectedExecution) return;
    const payload = await api<{ execution: WorkflowExecution; steps: ExecutionStep[] }>(`/api/executions/${selectedExecution.id}/cancel`, { method: 'POST' });
    setSelectedExecution(payload.execution);
    setSteps(payload.steps);
    await loadExecutions();
  }

  async function retryExecution() {
    if (!selectedExecution) return;
    const payload = await api<{ execution: WorkflowExecution; steps: ExecutionStep[] }>(`/api/executions/${selectedExecution.id}/retry`, { method: 'POST' });
    setSelectedExecution(payload.execution);
    setSteps(payload.steps);
    await loadExecutions();
  }

  async function approveExecution(approved: boolean) {
    if (!selectedExecution || !selectedExecution.current_node_id) return;
    const payload = await api<{ execution: WorkflowExecution; steps: ExecutionStep[] }>(`/api/executions/${selectedExecution.id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ nodeId: selectedExecution.current_node_id, approved, async: true }),
    });
    setSelectedExecution(payload.execution);
    setSteps(payload.steps);
    await loadExecutions();
    await loadEvents(payload.execution.id);
    await loadTasks();
  }

  async function recoverExecutions() {
    const payload = await api<{ recovered: string[] }>('/api/recover', { method: 'POST' });
    setMessage(`Recovered ${payload.recovered.length} executions.`);
    await loadExecutions();
  }

  async function loadEvents(executionId?: string) {
    const suffix = executionId ? `?executionId=${encodeURIComponent(executionId)}` : '';
    const payload = await api<{ events: AlosCurrentEvent[] }>(`/api/events${suffix}`);
    setEvents(payload.events);
  }

  async function loadTasks() {
    const payload = await api<{ tasks: WorkflowTask[] }>('/api/tasks');
    setTasks(payload.tasks);
  }

  async function updateTask(task: WorkflowTask, status: WorkflowTask['status']) {
    const payload = await api<{ task: WorkflowTask }>(`/api/tasks/${task.id}`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
    setTasks((items) => items.map((item) => (item.id === payload.task.id ? payload.task : item)));
  }

  async function loadSwarm() {
    const payload = await api<{ departments: Department[]; agents: Agent[] }>('/api/swarm');
    setDepartments(payload.departments);
    setAgents(payload.agents);
  }

  async function loadAudit() {
    const payload = await api<{ audit: Record<string, unknown>[] }>('/api/audit');
    setAudit(payload.audit);
  }

  function addNode(type: string, position?: { x: number; y: number }) {
    const spec = nodeTypeMap.get(type);
    if (!spec) return;
    const id = `node_${type}_${Date.now()}`;
    const config: Record<string, string | number | boolean | null> = {};
    for (const field of spec.configSchema) {
      config[field.key] = field.default ?? '';
    }
    updateGraph({
      ...graph,
      nodes: [
        ...graph.nodes,
        {
          id,
          type,
          name: spec.label,
          position: position || { x: 120 + graph.nodes.length * 36, y: 120 + graph.nodes.length * 24 },
          config,
          status: 'idle',
        },
      ],
    });
    setSelectedNodeId(id);
  }

  function validateCurrentGraph() {
    const result = validateGraph(graph, nodeTypes);
    setValidation(result);
    setMessage(result.valid ? 'Workflow DAG is valid.' : result.errors.join(' '));
  }

  function undo() {
    const previous = undoStack.current.pop();
    if (!previous) return;
    redoStack.current.push(graph);
    updateGraph(previous, false);
  }

  function redo() {
    const next = redoStack.current.pop();
    if (!next) return;
    undoStack.current.push(graph);
    updateGraph(next, false);
  }

  function exportWorkflow() {
    if (!workflow) return;
    const payload = JSON.stringify({ ...workflow, draft: graph }, null, 2);
    const blob = new Blob([payload], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${workflow.name.replace(/\s+/g, '-')}.alos_current.json`;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  function importWorkflow(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      void persistImportedWorkflow(String(reader.result));
    };
    reader.readAsText(file);
    event.target.value = '';
  }

  async function persistImportedWorkflow(raw: string) {
    try {
      const parsed = JSON.parse(raw);
      const draft = parsed.draft || parsed;
      if (!draft || !Array.isArray(draft.nodes) || !Array.isArray(draft.edges)) {
        throw new Error('Import must contain a workflow draft or graph with nodes and edges.');
      }
      const result = validateGraph(draft, nodeTypes);
      setValidation(result);
      if (!result.valid) {
        updateGraph(draft);
        setMessage(`Imported graph has validation errors: ${result.errors.join(' ')}`);
        return;
      }
      const created = await api<{ workflow: WorkflowDefinition }>('/api/workflows', {
        method: 'POST',
        body: JSON.stringify({
          name: parsed.name ? `${parsed.name} Import` : 'Imported AlosCurrent Workflow',
          description: parsed.description || '',
          draft,
          settings: parsed.settings,
          tags: parsed.metadata?.tags || [],
        }),
      });
      setWorkflows((items) => [created.workflow, ...items]);
      selectWorkflow(created.workflow);
      setMessage('Workflow imported and saved.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function currentAgentContext() {
    return {
      workflow: workflow ? { ...workflow, draft: graph } : null,
      validation,
      selectedExecution,
      steps,
      tasks: tasks.slice(0, 20),
      recentEvents: events.slice(0, 30),
      availableAgents: agents,
    };
  }

  function appendAgentMessage(next: AgentMessage) {
    setAgentMessages((items) => [...items, next].slice(-80));
  }

  async function connectAgent(): Promise<WebSocket> {
    const existing = agentSocketRef.current;
    if (existing && existing.readyState === WebSocket.OPEN) return existing;
    setAgentConnection('connecting');
    const session = await alosApi.createSession('Current workflow assistant');
    const socket = alosApi.openSocket(session.id);
    return await new Promise((resolve, reject) => {
      socket.onopen = () => {
        agentSocketRef.current = socket;
        setAgentConnection('open');
        resolve(socket);
      };
      socket.onerror = () => {
        setAgentConnection('error');
        reject(new Error('Current agent connection failed.'));
      };
      socket.onclose = () => {
        if (agentSocketRef.current === socket) agentSocketRef.current = null;
        setAgentConnection((current) => (current === 'open' ? 'idle' : current));
      };
      socket.onmessage = (event) => {
        let frame: ChatWsServerFrame;
        try {
          frame = JSON.parse(event.data) as ChatWsServerFrame;
        } catch {
          appendAgentMessage({ role: 'system', content: String(event.data), ts: Date.now() });
          return;
        }
        if (frame.type === 'chat_output') {
          const content = String(frame.content ?? '');
          appendAgentMessage({ role: 'agent', content, ts: Date.now() });
          const proposed = extractWorkflowProposal(content);
          if (proposed) {
            setProposalText(JSON.stringify(proposed, null, 2));
            setProposalStatus('Agent proposed a workflow graph. Review and validate it before applying.');
          }
        } else if (frame.type === 'status' || frame.type === 'system_log' || frame.type === 'setup_required') {
          const content = 'message' in frame ? frame.message : frame.content;
          appendAgentMessage({ role: 'system', content: String(content ?? ''), ts: Date.now() });
        } else if (frame.type === 'plan_approval_request' || frame.type === 'plan_request') {
          appendAgentMessage({ role: 'system', content: 'Agent requested plan approval in Chat. Use Chat for full run approval.', ts: Date.now() });
        }
      };
    });
  }

  async function askWorkflowAgent() {
    if (!agentRequest.trim()) return;
    try {
      const socket = await connectAgent();
      const text = [
        'Current workflow assistant request.',
        '',
        'Structured Current context:',
        JSON.stringify(currentAgentContext(), null, 2),
        '',
        'Rules:',
        '- Help the user design, inspect, or operate this workflow.',
        '- Do not bypass approval gates.',
        '- Any autonomous file or code write must use proposed patches and wait for the Chamber build/test gate.',
        '- For workflow edits, propose a complete WorkflowGraph JSON object with nodes, edges, and variables.',
        '- The user must review, validate, and apply any proposed graph manually in Current.',
        '',
        `User request: ${agentRequest.trim()}`,
      ].join('\n');
      socket.send(JSON.stringify({
        type: 'chat_input',
        text,
        module_context: {
          module_id: 'current',
          module_name: 'Current',
          captured_at: new Date().toISOString(),
          payload: currentAgentContext(),
        },
      } satisfies ChatWsClientFrame));
      appendAgentMessage({ role: 'user', content: agentRequest.trim(), ts: Date.now() });
      setAgentRequest('');
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : String(error);
      setAgentConnection('error');
      setProposalStatus(nextMessage);
    }
  }

  function extractWorkflowProposal(content: string): WorkflowGraph | null {
    const fenced = content.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1];
    const candidates = [fenced, content].filter(Boolean) as string[];
    for (const candidate of candidates) {
      try {
        const parsed = JSON.parse(candidate);
        const draft = parsed.draft || parsed;
        if (draft && Array.isArray(draft.nodes) && Array.isArray(draft.edges)) {
          return draft as WorkflowGraph;
        }
      } catch {
        // Keep scanning; assistant output may contain prose before JSON.
      }
    }
    return null;
  }

  function validateProposal() {
    try {
      const parsed = JSON.parse(proposalText);
      const draft = parsed.draft || parsed;
      if (!draft || !Array.isArray(draft.nodes) || !Array.isArray(draft.edges)) {
        throw new Error('Proposal must be a WorkflowGraph or workflow object with draft.nodes and draft.edges.');
      }
      const result = validateGraph(draft, nodeTypes);
      setProposalStatus(result.valid ? 'Proposal is valid and ready to apply.' : `Proposal is invalid: ${result.errors.join(' ')}`);
    } catch (error) {
      setProposalStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function applyProposal() {
    try {
      const parsed = JSON.parse(proposalText);
      const draft = parsed.draft || parsed;
      const result = validateGraph(draft, nodeTypes);
      setProposalStatus(result.valid ? 'Proposal applied to the draft. Save or publish when ready.' : `Proposal is invalid: ${result.errors.join(' ')}`);
      if (!result.valid) return;
      updateGraph(draft);
      setActiveTab('designer');
    } catch (error) {
      setProposalStatus(error instanceof Error ? error.message : String(error));
    }
  }

  const taskColumns: WorkflowTask['status'][] = ['ready', 'in_progress', 'review', 'blocked', 'done'];

  return (
    <div className="alos_current-container">
      <nav className="sidebar">
        <div className="brand">
          <span className="alos_current-logo">AC</span>
          <div>
            <h1>AlosCurrent</h1>
            <p>Workflow Orchestrator</p>
          </div>
        </div>
        {(['designer', 'monitor', 'tasks', 'swarm', 'agent', 'audit', 'settings'] as Tab[]).map((tab) => (
          <button key={tab} type="button" className={activeTab === tab ? 'nav-link active' : 'nav-link'} onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
        <div className="system-status">
          <span className="status-dot" />
          <span>{apiBase()}</span>
        </div>
      </nav>

      <main className="main-canvas">
        <header className="top-bar">
          <div>
            <h2>{workflow?.name || 'No workflow selected'}</h2>
            <p>{message}</p>
          </div>
          <div className="top-actions">
            <select value={workflow?.id || ''} onChange={(event) => {
              const next = workflows.find((item) => item.id === event.target.value);
              if (next) selectWorkflow(next);
            }}>
              {workflows.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <button type="button" onClick={() => void newWorkflow()}>New</button>
            <button type="button" onClick={() => void saveWorkflow()} disabled={!workflow}>Save</button>
            <button type="button" onClick={() => void publishWorkflow()} disabled={!workflow}>Publish</button>
            <button type="button" className="btn-primary" onClick={() => void executeWorkflow()} disabled={!workflow}>Execute</button>
          </div>
        </header>

        {activeTab === 'designer' && (
          <section className="designer-workspace">
            <section className="workflow-actions designer-command-bar">
              <button type="button" onClick={() => void duplicateWorkflow()} disabled={!workflow}>Duplicate</button>
              <button type="button" className="danger-button" onClick={() => void deleteWorkflow()} disabled={!workflow}>Archive</button>
              <button type="button" onClick={exportWorkflow} disabled={!workflow}>Export JSON</button>
              <label className="file-button">
                Import JSON
                <input type="file" accept="application/json,.json,.alos_current" onChange={importWorkflow} />
              </label>
              <button type="button" onClick={validateCurrentGraph}>Validate DAG</button>
              <span className={validation.valid ? 'pill ok' : 'pill error'}>{validation.valid ? 'Valid' : 'Invalid'}</span>
            </section>
            <WorkflowCanvas
              graph={graph}
              nodeTypes={nodeTypes}
              validation={validation}
              selectedNodeId={selectedNodeId}
              selectedEdgeId={selectedEdgeId}
              executionSteps={steps}
              onGraphChange={updateGraph}
              onSelectNode={setSelectedNodeId}
              onSelectEdge={setSelectedEdgeId}
              onAddNode={addNode}
              onValidate={validateCurrentGraph}
              onUndo={undo}
              onRedo={redo}
              agents={agents}
            />
          </section>
        )}

        {activeTab === 'monitor' && (
          <section className="dashboard-grid">
            <div className="glass-panel">
              <h3>Executions</h3>
              <button type="button" onClick={() => void recoverExecutions()}>Recover Pending</button>
              <div className="list-stack">
                {executions.map((execution) => (
                  <button key={execution.id} type="button" className="list-row" onClick={() => void loadExecution(execution.id)}>
                    <strong>{execution.status}</strong>
                    <span>{execution.id}</span>
                    <small>{execution.workflow_id}</small>
                  </button>
                ))}
              </div>
            </div>
            <div className="glass-panel wide-panel">
              <h3>Execution Detail</h3>
              {selectedExecution ? (
                <>
                  <div className="toolbar-line">
                    <span className={`pill ${selectedExecution.status}`}>{selectedExecution.status}</span>
                    <button type="button" onClick={() => void cancelExecution()}>Cancel</button>
                    <button type="button" onClick={() => void retryExecution()}>Retry</button>
                    <button type="button" onClick={() => void approveExecution(true)} disabled={selectedExecution.status !== 'paused'}>Approve</button>
                    <button type="button" onClick={() => void approveExecution(false)} disabled={selectedExecution.status !== 'paused'}>Reject</button>
                  </div>
                  <div className="timeline">
                    {steps.map((step) => (
                      <article key={step.id} className={`timeline-row ${step.status}`}>
                        <strong>{graph.nodes.find((node) => node.id === step.node_id)?.name || step.node_id}</strong>
                        <span>{step.status}</span>
                        <pre>{JSON.stringify(step.output, null, 2)}</pre>
                      </article>
                    ))}
                  </div>
                  <h4>Events</h4>
                  <EventList events={events} />
                </>
              ) : <p>Select or execute a workflow.</p>}
            </div>
          </section>
        )}

        {activeTab === 'tasks' && (
          <section className="task-board">
            {taskColumns.map((column) => (
              <div key={column} className="task-column">
                <h3>{column.replace(/_/g, ' ')}</h3>
                {tasks.filter((task) => task.status === column).map((task) => (
                  <article key={task.id} className="task-card">
                    <strong>{task.title}</strong>
                    <p>{task.description || task.acceptance_criteria}</p>
                    <span className="pill">{task.priority}</span>
                    <div className="task-actions">
                      {taskColumns.map((next) => (
                        <button key={next} type="button" onClick={() => void updateTask(task, next)}>{next}</button>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            ))}
          </section>
        )}

        {activeTab === 'swarm' && (
          <section className="dashboard-grid">
            <div className="glass-panel">
              <h3>Departments</h3>
              {departments.map((department) => (
                <article key={department.id} className="info-card">
                  <strong>{department.name}</strong>
                  <span>Head: {department.head_id}</span>
                  <span>Tier {department.authority_tier}</span>
                  <small>{department.capabilities.join(', ')}</small>
                </article>
              ))}
            </div>
            <div className="glass-panel">
              <h3>Agents</h3>
              {agents.map((agent) => (
                <article key={agent.id} className="info-card">
                  <strong>{agent.name}</strong>
                  <span>{agent.kind}</span>
                  <small>{agent.capabilities.join(', ')}</small>
                </article>
              ))}
            </div>
          </section>
        )}

        {activeTab === 'agent' && (
          <section className="dashboard-grid">
            <div className="glass-panel wide-panel">
              <h3>Agent-Assisted Workflow Design</h3>
              <textarea
                value={agentRequest}
                onChange={(event) => setAgentRequest(event.target.value)}
                placeholder="Ask an agent to inspect, improve, or explain this workflow..."
              />
              <div className="toolbar-line">
                <span className={`pill ${agentConnection}`}>{agentConnection}</span>
                <button type="button" className="btn-primary" onClick={() => void askWorkflowAgent()} disabled={!agentRequest.trim()}>
                  Ask Agent
                </button>
              </div>
              <div className="list-stack">
                {agentMessages.length === 0 ? (
                  <p>Ask for workflow help. Proposed graph changes stay in review until you validate and apply them.</p>
                ) : agentMessages.map((item) => (
                  <article key={`${item.ts}-${item.role}-${item.content.slice(0, 8)}`} className="info-card">
                    <strong>{item.role}</strong>
                    <pre>{item.content}</pre>
                  </article>
                ))}
              </div>
            </div>
            <div className="glass-panel">
              <h3>Proposal Review</h3>
              <textarea
                value={proposalText}
                onChange={(event) => setProposalText(event.target.value)}
                placeholder="Paste or review a proposed WorkflowGraph JSON object here."
              />
              <div className="toolbar-line">
                <button type="button" onClick={validateProposal} disabled={!proposalText.trim()}>Validate</button>
                <button type="button" className="btn-primary" onClick={applyProposal} disabled={!proposalText.trim()}>Apply To Draft</button>
              </div>
              {proposalStatus ? <p>{proposalStatus}</p> : null}
              <h4>Structured Context</h4>
              <pre className="audit-row">{JSON.stringify(currentAgentContext(), null, 2)}</pre>
            </div>
          </section>
        )}

        {activeTab === 'audit' && (
          <section className="glass-panel">
            <h3>Audit And Events</h3>
            <button type="button" onClick={() => { void loadAudit(); void loadEvents(); }}>Refresh</button>
            <EventList events={events} />
            <div className="list-stack">
              {audit.map((item, index) => <pre key={index} className="audit-row">{JSON.stringify(item, null, 2)}</pre>)}
            </div>
          </section>
        )}

        {activeTab === 'settings' && (
          <section className="glass-panel">
            <h3>Settings</h3>
            <label>
              ALOS sidecar
              <input value={apiBase()} readOnly />
            </label>
            <p>Current uses the authenticated ALOS sidecar session. API keys are managed by ALOS settings and login.</p>
            <p>{storedApiToken() ? 'Authenticated.' : 'Sign in to ALOS before using Current.'}</p>
          </section>
        )}
      </main>
    </div>
  );
}

function EventList({ events }: { events: AlosCurrentEvent[] }) {
  return (
    <div className="event-list">
      {events.map((event) => (
        <article key={event.id} className={`event-row ${event.level}`}>
          <strong>{event.type}</strong>
          <span>{event.message}</span>
          <small>{event.timestamp}</small>
        </article>
      ))}
    </div>
  );
}

export default App;
