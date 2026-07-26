// Central API client — all requests go through /api, proxied by Vite to localhost:8000

const BASE = "/api"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ── Stage metadata ─────────────────────────────────────────────────────────

export const STAGES = [
  "StrategicReview", "ProductOwner", "Architect", "Designer",
  "Security", "FileStructurePlanner", "BackendDeveloper",
  "FrontendDeveloper", "QA", "Document", "DevOps", "Retro",
] as const

export type StageName = (typeof STAGES)[number]

export const STAGE_LABELS: Record<StageName, string> = {
  StrategicReview:     "Strategic Review",
  ProductOwner:        "Product Owner",
  Architect:           "Architect",
  Designer:            "Designer",
  Security:            "Security",
  FileStructurePlanner:"File Planner",
  BackendDeveloper:    "Backend Dev",
  FrontendDeveloper:   "Frontend Dev",
  QA:                  "QA",
  Document:            "Docs",
  DevOps:              "DevOps",
  Retro:               "Retro",
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface ReadyStatus {
  status: "ready" | "degraded"
  ollama: "reachable" | "unreachable"
  model: string
  model_available: boolean
  database: "connected" | "error"
  timestamp: string
}

export interface ProjectSummary {
  project_id: string
  name: string
  status: string
  current_stage: string
  created_at: string
}

export interface ArtifactSummary {
  stage: string
  file: string
  json?: string
  attempt: number
  created_at: string
}

export interface ProjectDetail {
  project_id: string
  name: string
  description: string
  status: string
  current_stage: string
  stages_completed: string[]
  artifacts: ArtifactSummary[]
  workspace_path: string
}

export interface CreateProjectResult {
  project: {
    project_id: string
    name: string
    description: string
    workspace_path: string
    created_at: string
    current_stage: string
    status: string
  }
  success: boolean
  message: string
}

export interface WorkflowStatus {
  project_id: string
  state: string
  status: "not_started" | "running" | "paused" | "stopped" | "complete" | "failed"
  current_stage: string | null
  completed_stages: string[]
  failed_stage: string | null
  total_stages: number
  progress_percent: number
  requires_user_action?: boolean
  current_sprint?: number
  total_sprints?: number
  sprint_name?: string
  sprint_progress?: string
  estimated_completion?: string
}

export interface DesignReviewData {
  project_id: string
  state: string
  review_iteration: number
  design: Record<string, unknown>
  instructions: string
}

export interface LogEvent {
  id: number
  stage: string
  level: "info" | "warning" | "error"
  message: string
  created_at: string
}

export interface ProjectFiles {
  backend: string[]
  frontend: string[]
}

export interface FileContent {
  project_id: string
  area: string
  path: string
  content: string
}

export interface CostSummary {
  project_id: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  total_latency_ms: number
}

export interface ArtifactDetail {
  project_id: string
  stage: string
  attempt: number
  content: string
  structured: Record<string, unknown>
}

export interface ArtifactHistoryItem {
  attempt: number
  content: string
  structured: Record<string, unknown>
  approved: boolean
}

export interface AgentInfo {
  agent: string
  stage: string
  status: string
  llm_backed: boolean
  prompt_builder: string
  output_schema: string
}

export interface MemorySummary {
  project_id: string
  records: { key: string; value_preview: string; stored_at: string }[]
  lesson_count: number
  trajectory_count: number
  knowledge_entry_count: number
}

export interface LLMSettings {
  provider: string
  model: string
  base_url: string
  bedrock_region: string
  bedrock_api_key_set: boolean
}

export interface ProviderInfo {
  id: string
  label: string
  models: string[]
  requires_api_key: boolean
}

export interface QASession {
  project_id: string
  status: string
  total_questions: number
  answered: number
  current_question_index: number
  current_question: {
    index: number
    question: string
    category: string
    priority: string
    options: { value: string; label: string }[] | null
    allows_custom: boolean
    skippable: boolean
  } | null
  previous_answers: { question_index: number; question: string; answer: string }[]
  is_complete: boolean
}

export interface PerformanceData {
  stage: string
  total: number
  success_rate: number
  avg_retries: number
  avg_tokens: number
  avg_latency: number
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request<{ status: string }>("/health"),
  ready:  () => request<ReadyStatus>("/ready"),

  // Projects
  listProjects:  () => request<ProjectSummary[]>("/projects"),
  createProject: (name: string, description: string) =>
    request<CreateProjectResult>("/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  getProject:    (id: string) => request<ProjectDetail>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // Workflow
  startWorkflow: (projectId: string, req: string) =>
    request<{ project_id: string; state: string; success: boolean; message: string }>("/workflow/start", {
      method: "POST", body: JSON.stringify({ project_id: projectId, request: req }),
    }),
  getWorkflowStatus: (id: string) => request<WorkflowStatus>(`/workflow/${id}`),
  stopWorkflow:      (id: string) => request<{ stop_requested: boolean }>(`/workflow/${id}/stop`, { method: "POST" }),
  continueWorkflow:  (id: string) => request<{ success: boolean; message: string }>(`/workflow/${id}/continue`, { method: "POST" }),
  runStage:          (projectId: string, stage: string, req: string) =>
    request<{ success: boolean; message: string }>("/workflow/stage", {
      method: "POST", body: JSON.stringify({ project_id: projectId, stage, request: req }),
    }),

  // Design review
  getDesignReview:  (id: string) => request<DesignReviewData>(`/workflow/${id}/design-review`),
  postDesignReview: (id: string, approved: boolean, feedback?: string, modified_design?: Record<string, unknown>) =>
    request<{ state: string; message: string }>(`/workflow/${id}/design-review`, {
      method: "POST", body: JSON.stringify({ approved, feedback, modified_design }),
    }),

  // QA
  getQASession:    (id: string) => request<QASession>(`/workflow/${id}/qa`),
  answerQA:        (id: string, question_index: number, answer: string) =>
    request<{ saved: boolean; is_complete: boolean; next_question: unknown }>(`/workflow/${id}/qa/answer`, {
      method: "POST", body: JSON.stringify({ question_index, answer }),
    }),
  skipQA:          (id: string, question_index: number) =>
    request<{ skipped: boolean; is_complete: boolean }>(`/workflow/${id}/qa/skip`, {
      method: "POST", body: JSON.stringify({ question_index }),
    }),
  completeQA:      (id: string) =>
    request<{ status: string; message: string; state?: string }>(`/workflow/${id}/qa/complete`, { method: "POST" }),

  // Requirement changes
  submitChange:  (id: string, description: string) =>
    request<Record<string, unknown>>(`/workflow/${id}/change`, {
      method: "POST", body: JSON.stringify({ description }),
    }),
  confirmChange: (id: string, change_id: string, confirmed = true, comment = "") =>
    request<Record<string, unknown>>(`/workflow/${id}/change/confirm`, {
      method: "POST", body: JSON.stringify({ change_id, confirmed, comment }),
    }),
  cancelChange:  (id: string, change_id: string) =>
    request<Record<string, unknown>>(`/workflow/${id}/change/cancel`, {
      method: "POST", body: JSON.stringify({ change_id }),
    }),
  listChanges:   (id: string) =>
    request<{ changes: Record<string, unknown>[] }>(`/workflow/${id}/changes`),

  // Logs
  getLogs: (id: string, sinceId = 0) => request<LogEvent[]>(`/projects/${id}/logs?since_id=${sinceId}`),

  // Files
  getFiles:       (id: string) => request<ProjectFiles>(`/projects/${id}/files`),
  getFileContent: (id: string, area: string, path: string) =>
    request<FileContent>(`/projects/${id}/files/${area}/${path}`),
  getRunInstructions: (id: string) =>
    request<{ project_id: string; markdown: string }>(`/projects/${id}/run-instructions`),
  downloadUrl: (id: string) => `${BASE}/projects/${id}/download`,

  // Artifacts
  listArtifacts:     (id: string) => request<ArtifactSummary[]>(`/artifacts/${id}`),
  getArtifact:       (id: string, stage: string) => request<ArtifactDetail>(`/artifacts/${id}/${stage}`),
  getArtifactHistory:(id: string, stage: string) => request<ArtifactHistoryItem[]>(`/artifacts/${id}/${stage}/history`),

  // Metrics / memory / cost
  getCost:       (id: string) => request<CostSummary>(`/projects/${id}/cost`),
  getMemory:     (id: string) => request<MemorySummary>(`/memory/${id}`),
  getMetrics:    (id: string) => request<Record<string, unknown>>(`/projects/${id}/metrics`),
  getPerf:       (stage: string) => request<PerformanceData>(`/learning/performance/${stage}`),
  getPatterns:   () => request<{ patterns: unknown[] }>("/learning/patterns"),

  // Agents
  listAgents: () => request<AgentInfo[]>("/agents"),

  // Chat
  sendChat: (id: string, message: string) =>
    request<{ reply: string; action_taken?: string; stage_triggered?: string; artifacts_read?: string[] }>(
      `/projects/${id}/chat`, { method: "POST", body: JSON.stringify({ message }) },
    ),

  // Settings
  getLLMSettings:    () => request<LLMSettings>("/settings/llm"),
  updateLLMSettings: (update: Partial<LLMSettings & { bedrock_api_key: string }>) =>
    request<LLMSettings>("/settings/llm", { method: "POST", body: JSON.stringify(update) }),
  listProviders:     () => request<{ providers: ProviderInfo[] }>("/settings/providers"),

  // Validate / metrics
  validateProject: (id: string) => request<Record<string, unknown>>(`/projects/${id}/validate`),
}
