// Central API client — all requests go through /api, proxied by Vite to localhost:8000

const BASE = "/api"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// ── Auth token injection ──────────────────────────────────────────────────────
// Set by AuthProvider so all API calls automatically carry the Bearer token.
let _getToken: (() => string | null) | null = null
export function setTokenProvider(fn: () => string | null) { _getToken = fn }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = _getToken?.()
  const authHeader = token ? { "Authorization": `Bearer ${token}` } : {}
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeader, ...(init?.headers ?? {}) },
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

// Stage names MUST match the backend's Stage enum values exactly (what appears
// in stages_completed from the project.json / workflow status API).
export const STAGES = [
  "DomainResearch", "Clarifying",
  "StrategicReview", "ProductOwner", "Architect", "Designer",
  "Security", "SprintPlanning", "ScrumMaster", "FileStructurePlanner",
  "BackendDeveloper", "FrontendDeveloper", "Integration", "SprintDeploy", "SprintReview",
  "QA", "BugAnalyst", "DevOps", "Document", "Retro",
] as const

export type StageName = (typeof STAGES)[number]

export const STAGE_LABELS: Record<StageName, string> = {
  DomainResearch:       "Domain Research",
  Clarifying:           "Clarification Q&A",
  StrategicReview:      "Strategic Review",
  ProductOwner:         "Product Owner",
  Architect:            "Architect",
  Designer:             "Designer",
  Security:             "Security",
  SprintPlanning:       "Sprint Planner",
  ScrumMaster:          "Scrum Master",
  FileStructurePlanner: "File Planner",
  BackendDeveloper:     "Backend Dev",
  FrontendDeveloper:    "Frontend Dev",
  Integration:          "Integration",
  SprintDeploy:         "Sprint Deploy",
  SprintReview:         "Sprint Review",
  QA:                   "QA",
  BugAnalyst:           "Bug Analyst",
  DevOps:               "DevOps",
  Document:             "Docs",
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
  mode?: "full" | "quick"
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
  mode?: "full" | "quick"
  clarification_questions?: string[]
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

export interface CreateAndRunProjectResult {
  id: string
  name: string
  description: string
  status: string
  state: string
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
  clarification_questions?: string[]
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
  claude_api_key_set: boolean
  gemini_api_key_set: boolean
}

export interface LLMSettingsUpdate {
  provider?: string
  model?: string
  base_url?: string
  bedrock_region?: string
  bedrock_api_key?: string
  claude_api_key?: string
  gemini_api_key?: string
}

export interface ProviderInfo {
  id: string
  label: string
  models: string[]
  default_model: string
  requires_api_key: boolean
  api_key_field?: string
  notes: string
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

// ── R6: Integration types ───────────────────────────────────────────────────

export interface IntegrationEnvVar {
  name: string
  description: string
  required: boolean
}

export interface IntegrationService {
  name: string
  display_name?: string
  keywords: string[]
  description?: string
  env_vars: IntegrationEnvVar[]
  files?: string[]
}

export interface ProjectIntegrations {
  project_id: string
  detected_services: string[]
  integration_files: string[]
  env_vars_needed: { service: string; var_name: string; description: string; required: boolean }[]
}

// ── R7: Analytics types ─────────────────────────────────────────────────────

export interface AnalyticsOverview {
  total_projects: number
  total_stages_run: number
  total_tokens: number
  total_llm_calls: number
  total_latency_ms: number
  avg_tokens_per_project: number
  stage_breakdown: { stage: string; calls: number; avg_tokens: number; success_rate: number }[]
}

export interface AnalyticsLearning {
  total_lessons: number
  total_trajectories: number
  recent_lessons: { lesson_id: string; stage: string; title: string; created_at: string }[]
  top_patterns: { pattern: string; count: number }[]
}

// ── R8: Auth + Admin types ──────────────────────────────────────────────────

export interface AdminUser {
  user_id: string
  email: string
  role: "admin" | "developer" | "viewer"
  created_at: string
  is_active: boolean
}

// ── Gate types ──────────────────────────────────────────────────────────────

export interface GateInfo {
  gate: string
  state: string
  artifact?: Record<string, unknown>
  instructions?: string
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request<{ status: string }>("/health"),
  ready:  () => request<ReadyStatus>("/ready"),

  // Projects
  listProjects:  () => request<ProjectSummary[]>("/projects"),
  createProject: (name: string, description: string, mode: "full" | "quick" = "full") =>
    request<CreateProjectResult>("/projects", {
      method: "POST", body: JSON.stringify({ name, description, mode }),
    }),
  createAndRunProject: (name: string, description: string, mode: "full" | "quick" = "full") =>
    request<CreateAndRunProjectResult>("/projects/create-and-run", {
      method: "POST", body: JSON.stringify({ name, description, mode }),
    }),
  submitClarifications: (projectId: string, answers: Record<string, string>) =>
    request<{ status: string }>(`/projects/${projectId}/submit-clarifications`, {
      method: "POST", body: JSON.stringify({ answers }),
    }),
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
  runStage: (projectId: string, stage: string, req: string) =>
    request<{ success: boolean; message: string }>("/workflow/stage", {
      method: "POST", body: JSON.stringify({ project_id: projectId, stage, request: req }),
    }),

  // Human gates
  getCurrentGate: (id: string) => request<GateInfo | null>(`/workflow/${id}/gates/current`),
  approveGate:    (id: string, gate: string) =>
    request<{ success: boolean; message: string }>(`/workflow/${id}/gates/${gate}/approve`, { method: "POST" }),
  reviseGate:     (id: string, gate: string, feedback: string) =>
    request<{ success: boolean; message: string }>(`/workflow/${id}/gates/${gate}/revise`, {
      method: "POST", body: JSON.stringify({ feedback }),
    }),
  adjustSprintPlan: (id: string, feedback: string, max_sprints?: number) =>
    request<{ success: boolean; message: string }>(`/workflow/${id}/gates/sprint_plan/adjust`, {
      method: "POST", body: JSON.stringify({ feedback, max_sprints }),
    }),

  // Design review
  getDesignReview:  (id: string) => request<DesignReviewData>(`/workflow/${id}/design-review`),
  postDesignReview: (id: string, approved: boolean, feedback?: string, modified_design?: Record<string, unknown>) =>
    request<{ state: string; message: string }>(`/workflow/${id}/design-review`, {
      method: "POST", body: JSON.stringify({ approved, feedback, modified_design }),
    }),

  // QA
  getQASession: (id: string) => request<QASession>(`/workflow/${id}/qa`),
  answerQA:     (id: string, question_index: number, answer: string) =>
    request<{ saved: boolean; is_complete: boolean; next_question: unknown }>(`/workflow/${id}/qa/answer`, {
      method: "POST", body: JSON.stringify({ question_index, answer }),
    }),
  skipQA: (id: string, question_index: number) =>
    request<{ skipped: boolean; is_complete: boolean }>(`/workflow/${id}/qa/skip`, {
      method: "POST", body: JSON.stringify({ question_index }),
    }),
  completeQA: (id: string) =>
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
  cancelChange: (id: string, change_id: string) =>
    request<Record<string, unknown>>(`/workflow/${id}/change/cancel`, {
      method: "POST", body: JSON.stringify({ change_id }),
    }),
  listChanges: (id: string) =>
    request<{ changes: Record<string, unknown>[] }>(`/workflow/${id}/changes`),
  getDesignPreview: (id: string) =>
    request<{ html: string }>(`/workflow/${id}/design-preview`),

  // Logs
  getLogs: (id: string, sinceId = 0) => request<LogEvent[]>(`/projects/${id}/logs?since_id=${sinceId}`),

  // Files
  getFiles:           (id: string) => request<ProjectFiles>(`/projects/${id}/files`),
  getFileContent:     (id: string, area: string, path: string) =>
    request<FileContent>(`/projects/${id}/files/${area}/${path}`),
  getRunInstructions: (id: string) =>
    request<{ project_id: string; markdown: string }>(`/projects/${id}/run-instructions`),
  downloadUrl: (id: string) => `${BASE}/projects/${id}/download`,

  // Artifacts
  listArtifacts:      (id: string) => request<ArtifactSummary[]>(`/artifacts/${id}`),
  getArtifact:        (id: string, stage: string) => request<ArtifactDetail>(`/artifacts/${id}/${stage}`),
  getArtifactHistory: (id: string, stage: string) => request<ArtifactHistoryItem[]>(`/artifacts/${id}/${stage}/history`),

  // Metrics / memory / cost
  getCost:     (id: string) => request<CostSummary>(`/projects/${id}/cost`),
  getMemory:   (id: string) => request<MemorySummary>(`/memory/${id}`),
  getMetrics:  (id: string) => request<Record<string, unknown>>(`/projects/${id}/metrics`),
  getPerf:     (stage: string) => request<PerformanceData>(`/learning/performance/${stage}`),
  getPatterns: () => request<{ patterns: unknown[] }>("/learning/patterns"),

  // Agents
  listAgents: () => request<AgentInfo[]>("/agents"),

  // Chat
  sendChat: (id: string, message: string) =>
    request<{ reply: string; action_taken?: string; stage_triggered?: string; artifacts_read?: string[] }>(
      `/projects/${id}/chat`, { method: "POST", body: JSON.stringify({ message }) },
    ),

  // Settings
  getLLMSettings:    () => request<LLMSettings>("/settings/llm"),
  updateLLMSettings: (update: LLMSettingsUpdate) =>
    request<LLMSettings>("/settings/llm", { method: "POST", body: JSON.stringify(update) }),
  listProviders: () => request<{ providers: ProviderInfo[] }>("/settings/providers"),

  // Validate
  validateProject: (id: string) => request<Record<string, unknown>>(`/projects/${id}/validate`),

  // ── R6: Integrations ──────────────────────────────────────────────────────
  listIntegrationServices: () =>
    request<{ services: IntegrationService[] }>("/integrations/services"),
  detectIntegrations: (text: string) =>
    request<{ detected: string[] }>("/integrations/detect", {
      method: "POST", body: JSON.stringify({ text }),
    }),
  getProjectIntegrations: (id: string) =>
    request<ProjectIntegrations>(`/projects/${id}/integrations`),
  getProjectEnvVars: (id: string) =>
    request<{ env_vars: ProjectIntegrations["env_vars_needed"] }>(`/projects/${id}/integrations/env-vars`),

  // ── R7: Analytics ─────────────────────────────────────────────────────────
  getAnalyticsOverview: () => request<AnalyticsOverview>("/analytics/overview"),
  getProjectAnalytics:  (id: string) => request<Record<string, unknown>>(`/analytics/projects/${id}`),
  getStageAnalytics:    (stage: string) => request<Record<string, unknown>>(`/analytics/stage/${stage}`),
  getLearningAnalytics: () => request<AnalyticsLearning>("/analytics/learning"),

  // ── R8: Auth ──────────────────────────────────────────────────────────────
  authMe: () => request<{ user_id: string; email: string; role: string }>("/auth/me"),
  authLogin: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string; user_id: string; email: string; role: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ email, password }) },
    ),
  authRegister: (email: string, password: string) =>
    request<{ user_id: string; email: string; role: string }>(
      "/auth/register", { method: "POST", body: JSON.stringify({ email, password }) },
    ),
  authLogout: (refresh_token?: string) =>
    request<{ message: string }>("/auth/logout", {
      method: "POST", body: JSON.stringify({ refresh_token }),
    }),
  authChangePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>("/auth/change-password", {
      method: "POST", body: JSON.stringify({ current_password, new_password }),
    }),

  // ── R8: Admin ─────────────────────────────────────────────────────────────
  adminListUsers:  () => request<{ users: AdminUser[] }>("/admin/users"),
  adminUpdateRole: (user_id: string, role: string) =>
    request<{ user_id: string; role: string }>(`/admin/users/${user_id}/role`, {
      method: "PUT", body: JSON.stringify({ role }),
    }),
  adminDeleteUser: (user_id: string) =>
    request<{ message: string }>(`/admin/users/${user_id}`, { method: "DELETE" }),
}
