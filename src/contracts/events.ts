// CONTRACT VERSION: 1
// LAST CHANGED: 2026-04-15
// BREAKING CHANGES ALLOWED THROUGH: v0.x. LOCKED at v1.0.

/**
 * AlosEvent — discriminated union of all events in the system.
 *
 * Every event MUST carry a `timestamp` field (Unix milliseconds).
 * This is mandated by RFC-0005 Decision 7.
 */
export type AlosEvent =
  // Forge events
  | { type: 'forge.file.changed'; path: string; timestamp: number }
  | { type: 'forge.file.saved'; path: string; timestamp: number }
  | { type: 'forge.file.created'; path: string; timestamp: number }
  | { type: 'forge.file.deleted'; path: string; timestamp: number }
  // Atlas events
  | { type: 'atlas.index.started'; root: string; timestamp: number }
  | {
      type: 'atlas.index.complete'
      root: string
      symbols: number
      timestamp: number
    }
  | { type: 'atlas.workspace.opened'; root: string; timestamp: number }
  // Current events
  | {
      type: 'current.workflow.started'
      workflowId: string
      runId: string
      timestamp: number
    }
  | {
      type: 'current.workflow.completed'
      runId: string
      status: 'ok' | 'error'
      timestamp: number
    }
  | {
      type: 'current.workflow.step.started'
      runId: string
      stepId: string
      timestamp: number
    }
  | {
      type: 'current.workflow.step.completed'
      runId: string
      stepId: string
      status: string
      timestamp: number
    }
  // Agent events
  | {
      type: 'agent.turn.started'
      conversationId: string
      agentId: string
      timestamp: number
    }
  | {
      type: 'agent.turn.completed'
      conversationId: string
      agentId: string
      tokens: number
      timestamp: number
    }
  // Agent step events (from RFC-0002)
  | {
      type: 'current.agent_step.turn_started'
      runId: string
      stepId: string
      turn: number
      agentId: string
      timestamp: number
    }
  | {
      type: 'current.agent_step.turn_completed'
      runId: string
      stepId: string
      turn: number
      agentId: string
      tokensIn: number
      tokensOut: number
      toolCalls: unknown[]
      timestamp: number
    }
  | {
      type: 'current.agent_step.tool_call'
      runId: string
      stepId: string
      turn: number
      toolName: string
      status: string
      durationMs: number
      timestamp: number
    }
  // Approval events (from RFC-0004)
  | { type: 'core.approval.requested'; request: unknown; timestamp: number }
  | {
      type: 'core.approval.resolved'
      id: string
      status: string
      resolvedAt: string
      actor: string | null
      timestamp: number
    }
  | {
      type: 'core.approval.cancelled'
      id: string
      cancelledAt: string
      timestamp: number
    }
  // Module badge event (from RFC-0001)
  | {
      type: 'module.badge.set'
      moduleId: string
      badge: number | 'dot' | null
      timestamp: number
    }

export type AlosEventType = AlosEvent['type']
