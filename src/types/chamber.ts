export interface ChamberSession {
  id: string
  name: string
  status: string
  stack: string
  age_seconds: number
}

export interface ChamberEvidence {
  command: string
  status: string
  exit_code?: number
  duration_seconds?: number
  stdout?: string
  stderr?: string
}

export interface ChamberGate {
  id: string
  patch_id: string
  file: string
  risk?: string
  rationale?: string
  commands: string[]
  status: 'staged' | 'running' | 'passed' | 'failed' | 'blocked' | 'written' | 'overridden' | string
  evidence: ChamberEvidence[]
  blocked_reason?: string
  override?: { actor?: string; approved_at?: string } | null
  created_at?: string
  updated_at?: string
}

export interface ChamberListResponse {
  chambers: ChamberSession[]
}

export interface ChamberGatesResponse {
  gates: ChamberGate[]
}

export interface ChamberGateSummary {
  total: number
  counts: Record<string, number>
  gates: ChamberGate[]
}
