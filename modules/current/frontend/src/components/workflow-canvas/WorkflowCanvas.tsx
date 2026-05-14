import { useMemo, useRef, useState, type PointerEvent, type WheelEvent } from 'react';
import type {
  Agent,
  ConfigField,
  ExecutionStep,
  NodeType,
  ValidationResult,
  WorkflowEdge,
  WorkflowGraph,
  WorkflowNode,
} from '../../types/workflow';

type PendingPort = {
  nodeId: string;
  portId: string;
};

type CanvasProps = {
  graph: WorkflowGraph;
  nodeTypes: NodeType[];
  validation: ValidationResult;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  executionSteps: ExecutionStep[];
  onGraphChange: (graph: WorkflowGraph) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onAddNode: (type: string, position?: { x: number; y: number }) => void;
  onValidate: () => void;
  onUndo: () => void;
  onRedo: () => void;
  agents: Agent[];
};

const NODE_WIDTH = 184;
const NODE_HEIGHT = 84;
let edgeIdCounter = 0;

function createEdgeId(): string {
  edgeIdCounter += 1;
  return `edge_${edgeIdCounter}`;
}

export default function WorkflowCanvas({
  graph,
  nodeTypes,
  validation,
  selectedNodeId,
  selectedEdgeId,
  executionSteps,
  onGraphChange,
  onSelectNode,
  onSelectEdge,
  onAddNode,
  onValidate,
  onUndo,
  onRedo,
  agents,
}: CanvasProps) {
  const [pendingPort, setPendingPort] = useState<PendingPort | null>(null);
  const [dragging, setDragging] = useState<{ nodeId: string; offsetX: number; offsetY: number } | null>(null);
  const [panning, setPanning] = useState<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const registry = useMemo(() => new Map(nodeTypes.map((node) => [node.type, node])), [nodeTypes]);
  const stepStatus = useMemo(() => {
    const latest = new Map<string, string>();
    for (const step of executionSteps) latest.set(step.node_id, step.status);
    return latest;
  }, [executionSteps]);

  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId) || null;
  const selectedSpec = selectedNode ? registry.get(selectedNode.type) || null : null;

  function screenToWorld(clientX: number, clientY: number) {
    const rect = canvasRef.current?.getBoundingClientRect();
    const localX = clientX - (rect?.left ?? 0);
    const localY = clientY - (rect?.top ?? 0);
    return {
      x: (localX - view.x) / view.scale,
      y: (localY - view.y) / view.scale,
    };
  }

  function addNodeFromPalette(type: string) {
    if (!canvasRef.current) {
      onAddNode(type);
      return;
    }
    const center = screenToWorld(
      canvasRef.current.getBoundingClientRect().left + canvasRef.current.clientWidth / 2,
      canvasRef.current.getBoundingClientRect().top + canvasRef.current.clientHeight / 2,
    );
    onAddNode(type, {
      x: Math.round(center.x - NODE_WIDTH / 2 + graph.nodes.length * 18),
      y: Math.round(center.y - NODE_HEIGHT / 2 + graph.nodes.length * 14),
    });
  }

  function updateNode(nodeId: string, patch: Partial<WorkflowNode>) {
    onGraphChange({
      ...graph,
      nodes: graph.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch } : node)),
    });
  }

  function updateConfig(nodeId: string, key: string, value: string | number | boolean | null) {
    onGraphChange({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === nodeId ? { ...node, config: { ...node.config, [key]: value } } : node,
      ),
    });
  }

  function deleteSelected() {
    if (selectedNodeId) {
      onGraphChange({
        ...graph,
        nodes: graph.nodes.filter((node) => node.id !== selectedNodeId),
        edges: graph.edges.filter((edge) => edge.sourceNodeId !== selectedNodeId && edge.targetNodeId !== selectedNodeId),
      });
      onSelectNode(null);
    } else if (selectedEdgeId) {
      onGraphChange({ ...graph, edges: graph.edges.filter((edge) => edge.id !== selectedEdgeId) });
      onSelectEdge(null);
    }
  }

  function beginDrag(event: PointerEvent<HTMLDivElement>, node: WorkflowNode) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const pointer = screenToWorld(event.clientX, event.clientY);
    onSelectNode(node.id);
    onSelectEdge(null);
    setDragging({
      nodeId: node.id,
      offsetX: pointer.x - node.position.x,
      offsetY: pointer.y - node.position.y,
    });
  }

  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    const pointer = screenToWorld(event.clientX, event.clientY);
    updateNode(dragging.nodeId, {
      position: {
        x: Math.round(pointer.x - dragging.offsetX),
        y: Math.round(pointer.y - dragging.offsetY),
      },
    });
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragging) event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(null);
  }

  function beginPan(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('button,input,select,textarea,label,.workflow-node,.wire,.node-palette,.config-panel,.canvas-toolbar,.designer-command-bar')) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setPanning({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: view.x,
      originY: view.y,
    });
  }

  function movePan(event: PointerEvent<HTMLDivElement>) {
    if (!panning || panning.pointerId !== event.pointerId) return;
    setView((prev) => ({
      ...prev,
      x: Math.round(panning.originX + event.clientX - panning.startX),
      y: Math.round(panning.originY + event.clientY - panning.startY),
    }));
  }

  function endPan(event: PointerEvent<HTMLDivElement>) {
    if (!panning || panning.pointerId !== event.pointerId) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setPanning(null);
  }

  function zoomAt(nextScale: number, clientX: number, clientY: number) {
    if (!canvasRef.current) {
      setView((prev) => ({ ...prev, scale: nextScale }));
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const worldX = (localX - view.x) / view.scale;
    const worldY = (localY - view.y) / view.scale;
    setView({
      x: Math.round(localX - worldX * nextScale),
      y: Math.round(localY - worldY * nextScale),
      scale: nextScale,
    });
  }

  function handleWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const nextScale = Math.max(0.35, Math.min(2, view.scale * (event.deltaY > 0 ? 0.92 : 1.08)));
    zoomAt(nextScale, event.clientX, event.clientY);
  }

  function connectTo(targetNodeId: string, targetPort: string) {
    if (!pendingPort || pendingPort.nodeId === targetNodeId) {
      setPendingPort(null);
      return;
    }
    const id = createEdgeId();
    const nextEdge: WorkflowEdge = {
      id,
      sourceNodeId: pendingPort.nodeId,
      sourcePort: pendingPort.portId,
      targetNodeId,
      targetPort,
    };
    onGraphChange({ ...graph, edges: [...graph.edges, nextEdge] });
    setPendingPort(null);
  }

  function edgePath(edge: WorkflowEdge): string {
    const source = graph.nodes.find((node) => node.id === edge.sourceNodeId);
    const target = graph.nodes.find((node) => node.id === edge.targetNodeId);
    if (!source || !target) return '';
    const sx = source.position.x + NODE_WIDTH;
    const sy = source.position.y + NODE_HEIGHT / 2;
    const tx = target.position.x;
    const ty = target.position.y + NODE_HEIGHT / 2;
    const dx = Math.max(70, Math.abs(tx - sx) * 0.45);
    return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
  }

  function fitView() {
    if (!graph.nodes.length || !canvasRef.current) {
      setView({ x: 0, y: 0, scale: 1 });
      return;
    }
    const bounds = graph.nodes.reduce(
      (box, node) => ({
        minX: Math.min(box.minX, node.position.x),
        minY: Math.min(box.minY, node.position.y),
        maxX: Math.max(box.maxX, node.position.x + NODE_WIDTH),
        maxY: Math.max(box.maxY, node.position.y + NODE_HEIGHT),
      }),
      { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
    );
    const width = Math.max(bounds.maxX - bounds.minX, NODE_WIDTH);
    const height = Math.max(bounds.maxY - bounds.minY, NODE_HEIGHT);
    const availableWidth = Math.max(canvasRef.current.clientWidth - 80, 320);
    const availableHeight = Math.max(canvasRef.current.clientHeight - 80, 240);
    const scale = Math.max(0.5, Math.min(1.4, availableWidth / width, availableHeight / height));
    setView({
      x: Math.round(40 - bounds.minX * scale),
      y: Math.round(40 - bounds.minY * scale),
      scale,
    });
  }

  return (
    <div className="designer-shell">
      <aside className="node-palette">
        <div className="panel-heading">Node Library</div>
        <div className="palette-scroll">
          {nodeTypes.map((nodeType) => (
            <button key={nodeType.type} className="palette-item" type="button" onClick={() => addNodeFromPalette(nodeType.type)}>
              <span>{nodeType.icon}</span>
              <strong>{nodeType.label}</strong>
              <small>{nodeType.category}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="canvas-stage">
        <div className="canvas-toolbar">
          <button type="button" onClick={onValidate}>Validate</button>
          <button type="button" onClick={onUndo}>Undo</button>
          <button type="button" onClick={onRedo}>Redo</button>
          <button type="button" onClick={fitView}>Fit View</button>
          <button type="button" onClick={() => zoomAt(Math.max(0.35, view.scale - 0.1), window.innerWidth / 2, window.innerHeight / 2)}>Zoom Out</button>
          <button type="button" onClick={() => zoomAt(Math.min(2, view.scale + 0.1), window.innerWidth / 2, window.innerHeight / 2)}>Zoom In</button>
          <button type="button" className="danger-button" onClick={deleteSelected} disabled={!selectedNodeId && !selectedEdgeId}>Delete Selected</button>
          <span className={validation.valid ? 'pill ok' : 'pill error'}>{validation.valid ? 'DAG valid' : `${validation.errors.length} errors`}</span>
        </div>
        <div
          ref={canvasRef}
          className={panning ? 'workflow-canvas panning' : 'workflow-canvas'}
          onPointerDown={beginPan}
          onPointerMove={movePan}
          onPointerUp={endPan}
          onPointerCancel={endPan}
          onWheel={handleWheel}
          onClick={() => { onSelectNode(null); onSelectEdge(null); }}
        >
          <div className="canvas-transform" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
            <svg className="wire-layer">
              {graph.edges.map((edge) => (
                <path
                  key={edge.id}
                  d={edgePath(edge)}
                  className={edge.id === selectedEdgeId ? 'wire selected' : 'wire'}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelectEdge(edge.id);
                    onSelectNode(null);
                  }}
                />
              ))}
            </svg>
            {graph.nodes.map((node) => {
              const spec = registry.get(node.type);
              const status = stepStatus.get(node.id) || node.status;
              return (
                <div
                  key={node.id}
                  className={`workflow-node ${selectedNodeId === node.id ? 'selected' : ''} status-${status}`}
                  style={{ left: node.position.x, top: node.position.y }}
                  onPointerDown={(event) => beginDrag(event, node)}
                  onPointerMove={moveDrag}
                  onPointerUp={endDrag}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelectNode(node.id);
                    onSelectEdge(null);
                  }}
                >
                  <header>
                    <span>{spec?.icon || '[]'}</span>
                    <strong>{node.name}</strong>
                  </header>
                  <p>{spec?.label || node.type}</p>
                  <div className="port-column inputs">
                    {(spec?.inputs || []).map((port) => (
                      <button
                        key={port.id}
                        type="button"
                        className="port input"
                        title={port.label}
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={(event) => {
                          event.stopPropagation();
                          connectTo(node.id, port.id);
                        }}
                      />
                    ))}
                  </div>
                  <div className="port-column outputs">
                    {(spec?.outputs || []).map((port) => (
                      <button
                        key={port.id}
                        type="button"
                        className={pendingPort?.nodeId === node.id && pendingPort.portId === port.id ? 'port output pending' : 'port output'}
                        title={port.label}
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={(event) => {
                          event.stopPropagation();
                          setPendingPort({ nodeId: node.id, portId: port.id });
                        }}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {(selectedNode && selectedSpec) || selectedEdgeId ? (
        <aside className="config-panel">
          <div className="panel-heading">Configuration</div>
          {selectedNode && selectedSpec ? (
          <div className="config-stack">
            <label>
              Node name
              <input value={selectedNode.name} onChange={(event) => updateNode(selectedNode.id, { name: event.target.value })} />
            </label>
            {selectedSpec.configSchema.map((field) => (
              <ConfigInput
                key={field.key}
                field={field}
                value={selectedNode.config[field.key] ?? field.default ?? ''}
                agents={agents}
                onChange={(value) => updateConfig(selectedNode.id, field.key, value)}
              />
            ))}
            <div className="node-json">
              <strong>Node JSON</strong>
              <pre>{JSON.stringify(selectedNode, null, 2)}</pre>
            </div>
          </div>
          ) : (
            <div className="node-json"><strong>Selected edge</strong><pre>{JSON.stringify(graph.edges.find((edge) => edge.id === selectedEdgeId), null, 2)}</pre></div>
          )}
        </aside>
      ) : null}
    </div>
  );
}

function ConfigInput({
  field,
  value,
  agents,
  onChange,
}: {
  field: ConfigField;
  value: string | number | boolean | null;
  agents: Agent[];
  onChange: (value: string | number | boolean | null) => void;
}) {
  if (field.type === 'agent_select') {
    return (
      <label>
        {field.label}
        <select value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          <option value="">-- Select Agent --</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name} ({agent.kind})
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (field.type === 'boolean') {
    return (
      <label className="check-row">
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        {field.label}
      </label>
    );
  }
  if (field.type === 'select') {
    return (
      <label>
        {field.label}
        <select value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
    );
  }
  if (field.type === 'text') {
    return (
      <label>
        {field.label}
        <textarea value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} />
      </label>
    );
  }
  return (
    <label>
      {field.label}
      <input
        type={field.type === 'number' ? 'number' : field.type === 'secret' ? 'password' : 'text'}
        value={String(value ?? '')}
        onChange={(event) => onChange(field.type === 'number' ? Number(event.target.value) : event.target.value)}
      />
    </label>
  );
}
