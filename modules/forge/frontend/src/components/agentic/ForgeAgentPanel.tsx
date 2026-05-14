import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box, Button, TextField } from '@mui/material';
import { api } from '@/api';
import type { ChatWsClientFrame, ChatWsServerFrame, RunPlan } from '@/types/api';
import { useIDEStore } from '../../store/useIDEStore';

interface AgentMessage {
  role: 'user' | 'agent' | 'system';
  content: string;
  ts: number;
}

interface PendingApproval {
  kind: 'plan' | 'patch' | 'write';
  approvalId: string;
  title: string;
  detail?: string;
  diff?: string;
}

function formatFrameMessage(frame: ChatWsServerFrame): AgentMessage | null {
  if (frame.type === 'chat_output') {
    return { role: 'agent', content: String(frame.content ?? ''), ts: Date.now() };
  }
  if (frame.type === 'status' || frame.type === 'system_log' || frame.type === 'setup_required') {
    const content = 'message' in frame ? frame.message : frame.content;
    return { role: 'system', content: String(content ?? ''), ts: Date.now() };
  }
  if (frame.type === 'execution_complete') {
    return { role: 'system', content: 'Agent run completed.', ts: Date.now() };
  }
  if (frame.type === 'plan_rejected') {
    return { role: 'system', content: String(frame.message ?? 'Plan was rejected.'), ts: Date.now() };
  }
  return null;
}

function stringifyPlan(plan: RunPlan | undefined): string {
  if (!plan) return 'No plan details were supplied.';
  return JSON.stringify(plan, null, 2);
}

const ForgeAgentPanel: React.FC = () => {
  const [request, setRequest] = useState('');
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [connection, setConnection] = useState<'idle' | 'connecting' | 'open' | 'error'>('idle');
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const getAgentContext = useIDEStore((state) => state.getAgentContext);
  const contextJson = useMemo(() => JSON.stringify(getAgentContext(), null, 2), [getAgentContext]);

  useLayoutEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  const appendMessage = useCallback((message: AgentMessage) => {
    setMessages((prev) => [...prev, message].slice(-80));
  }, []);

  const sendFrame = useCallback((frame: ChatWsClientFrame) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setLastError('Forge agent connection is not open.');
      return;
    }
    socket.send(JSON.stringify(frame));
  }, []);

  const connect = useCallback(async (): Promise<WebSocket> => {
    const existing = socketRef.current;
    if (existing && existing.readyState === WebSocket.OPEN) return existing;
    setConnection('connecting');
    setLastError(null);
    const session = await api.createSession('Forge agent');
    const socket = api.openSocket(session.id);
    return await new Promise((resolve, reject) => {
      socket.onopen = () => { socketRef.current = socket; setConnection('open'); resolve(socket); };
      socket.onerror = () => { setConnection('error'); reject(new Error('WebSocket connection failed.')); };
      socket.onclose = () => { if (socketRef.current === socket) socketRef.current = null; setConnection((c) => (c === 'open' ? 'idle' : c)); };
      socket.onmessage = (event) => {
        let frame: ChatWsServerFrame;
        try { frame = JSON.parse(event.data) as ChatWsServerFrame; }
        catch { appendMessage({ role: 'system', content: String(event.data), ts: Date.now() }); return; }
        const msg = formatFrameMessage(frame);
        if (msg) appendMessage(msg);
        if (frame.type === 'plan_approval_request' || frame.type === 'plan_request') {
          setPendingApproval({ kind: 'plan', approvalId: String(frame.approval_id), title: 'Plan approval required', detail: stringifyPlan(frame.plan as RunPlan | undefined) });
        }
        if (frame.type === 'patch_request') {
          const proposal = frame.proposal as { file?: unknown; diff?: unknown } | undefined;
          setPendingApproval({ kind: 'patch', approvalId: String(frame.approval_id), title: 'Patch approval required', detail: typeof proposal?.file === 'string' ? `File: ${proposal.file}` : undefined, diff: typeof proposal?.diff === 'string' ? proposal.diff : undefined });
        }
        if (frame.type === 'auth_request') {
          setPendingApproval({ kind: 'write', approvalId: String(frame.approval_id), title: 'Disk write approval required', detail: typeof frame.file_path === 'string' ? `File: ${frame.file_path}` : undefined, diff: typeof frame.diff === 'string' ? frame.diff : undefined });
        }
      };
    });
  }, [appendMessage]);

  const submitRequest = async () => {
    if (!request.trim()) return;
    try {
      const socket = await connect();
      const contextSnapshot = getAgentContext();
      const text = ['Forge IDE request.', '', 'Structured Forge context:', JSON.stringify(contextSnapshot, null, 2), '', 'Rules:', '- Help the user program from this Forge context.', '- Do not write directly to disk.', '- Use proposed patches for file changes so the user can review them.', '- Autonomous programming writes must wait for the Chamber build/test gate before disk mutation.', '', `User request: ${request.trim()}`].join('\n');
      socket.send(JSON.stringify({ type: 'chat_input', text, module_context: { module_id: 'forge', module_name: 'Forge', captured_at: new Date().toISOString(), payload: contextSnapshot } } satisfies ChatWsClientFrame));
      appendMessage({ role: 'user', content: request.trim(), ts: Date.now() });
      setRequest('');
    } catch (error) {
      setConnection('error');
      setLastError(error instanceof Error ? error.message : String(error));
    }
  };

  const approvePending = () => {
    if (!pendingApproval) return;
    sendFrame(pendingApproval.kind === 'plan' ? { type: 'plan_response', approval_id: pendingApproval.approvalId, approved: true } : { type: 'auth_response', approval_id: pendingApproval.approvalId, approved: true });
    setPendingApproval(null);
  };

  const rejectPending = () => {
    if (!pendingApproval) return;
    sendFrame(pendingApproval.kind === 'plan' ? { type: 'plan_response', approval_id: pendingApproval.approvalId, approved: false } : { type: 'auth_response', approval_id: pendingApproval.approvalId, approved: false });
    setPendingApproval(null);
  };

  return (
    // Outer: two-column grid. Left = chat. Right = context panel.
    // minHeight:0 on the grid so it doesn't expand past its container.
    <Box sx={{ height: '100%', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 1, minHeight: 0 }}>

      {/* ── Left column: input at top, messages fill the rest ── */}
      {/* minHeight:0 is the key — without it a flex child ignores overflow:auto on its children */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, minHeight: 0 }}>

        {/* Input row */}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexShrink: 0 }}>
          <TextField
            size="small"
            fullWidth
            multiline
            maxRows={3}
            placeholder="Ask for help… (Cmd+Enter to send)"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submitRequest(); }}
            sx={{
              '& .MuiInputBase-root': { fontSize: '0.85rem', bgcolor: '#1e293b', color: '#e2e8f0' },
              '& .MuiOutlinedInput-notchedOutline': { borderColor: '#334155' },
            }}
          />
          <Button
            variant="contained"
            size="small"
            disabled={!request.trim() || !!pendingApproval || connection === 'connecting'}
            onClick={() => void submitRequest()}
            sx={{ minWidth: 88, flexShrink: 0, textTransform: 'none', bgcolor: '#4f46e5' }}
          >
            {connection === 'connecting' ? 'Connecting…' : 'Ask Agent'}
          </Button>
        </Box>

        {lastError && (
          <Box sx={{ color: '#fca5a5', fontSize: '0.8rem', flexShrink: 0 }}>{lastError}</Box>
        )}

        {pendingApproval && (
          <Box sx={{ border: '1px solid #334155', borderRadius: '6px', p: 1.5, bgcolor: '#111827', flexShrink: 0 }}>
            <Box sx={{ fontSize: '0.85rem', fontWeight: 700, color: '#e2e8f0' }}>{pendingApproval.title}</Box>
            {pendingApproval.detail && <Box sx={{ mt: 0.5, fontSize: '0.8rem', color: '#94a3b8', whiteSpace: 'pre-wrap' }}>{pendingApproval.detail}</Box>}
            {pendingApproval.diff && <Box sx={{ mt: 0.75, maxHeight: 120, overflow: 'auto', fontFamily: 'monospace', fontSize: '0.72rem', color: '#cbd5e1', whiteSpace: 'pre-wrap' }}>{pendingApproval.diff}</Box>}
            <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
              <Button size="small" variant="contained" disabled={pendingApproval.kind !== 'plan'} onClick={approvePending} sx={{ textTransform: 'none', bgcolor: '#10b981' }}>
                {pendingApproval.kind === 'plan' ? 'Approve Plan' : 'Chamber Required'}
              </Button>
              <Button size="small" variant="outlined" onClick={rejectPending} sx={{ textTransform: 'none', borderColor: '#475569', color: '#cbd5e1' }}>Reject</Button>
            </Box>
          </Box>
        )}

        {/* Messages — flex:1 + minHeight:0 makes this shrink and scroll */}
        <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', border: '1px solid #1e293b', borderRadius: '6px', p: 1.5, bgcolor: '#0a0f1e' }}>
          {messages.length === 0 ? (
            <Box sx={{ color: '#475569', fontSize: '0.82rem' }}>
              Assisted programming starts here. Solo editing still works without this panel.
            </Box>
          ) : messages.map((m) => (
            <Box key={`${m.ts}-${m.role}-${m.content.slice(0, 12)}`} sx={{ mb: 1.5 }}>
              <Box sx={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', mb: 0.25, color: m.role === 'user' ? '#60a5fa' : m.role === 'agent' ? '#a78bfa' : '#94a3b8' }}>
                {m.role === 'user' ? 'You' : m.role === 'agent' ? 'Agent' : 'System'}
              </Box>
              <Box sx={{ fontSize: '0.84rem', color: m.role === 'system' ? '#94a3b8' : '#e2e8f0', whiteSpace: 'pre-wrap', lineHeight: 1.55, fontFamily: m.role === 'system' ? 'monospace' : 'inherit' }}>
                {m.content}
              </Box>
            </Box>
          ))}
          <div ref={messagesEndRef} />
        </Box>
      </Box>

      {/* ── Right column: context panel ── */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, minHeight: 0 }}>
        <Box sx={{ border: '1px solid #1e293b', borderRadius: '6px', p: 1, bgcolor: '#0a0f1e', flexShrink: 0 }}>
          <Box sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Mode</Box>
          <Box sx={{ mt: 0.5, fontSize: '0.75rem', color: '#cbd5e1' }}>
            Assisted programming enabled. Writes blocked until Chamber gates pass.
          </Box>
        </Box>
        <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', border: '1px solid #1e293b', borderRadius: '6px', p: 1, bgcolor: '#0a0f1e' }}>
          <Box sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', mb: 0.75 }}>Agent Context</Box>
          <Box sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', fontSize: '0.68rem', color: '#64748b' }}>{contextJson}</Box>
        </Box>
      </Box>

    </Box>
  );
};

export default ForgeAgentPanel;
