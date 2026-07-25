// API client for AI DevOS backend. All requests go through /api, proxied by
// Vite's dev server to http://localhost:8000 (see vite.config.ts) -- this file
// never needs to know the backend's real origin.

const BASE = "/api"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      // ignore -- fall back to statusText
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// ---------------------------------------------------------------- Stages

export const STAGES = [
  "StrategicReview",
  "ProductOwner",
  "Architect",
  "Designer",
  "Security",
  "FileStructurePlanner",
  "BackendDeveloper",
  "FrontendDeveloper",
  "QA",
  "Document",
  "DevOps",
  "Retro",
] as const

export type StageName = (typeof STAGES)[number]

export const STAGE_LABELS: Record<StageName, string> = {
  StrategicReview: "Strategic Review",
  ProductOwner: "Product Owner",
  Architect: "Architect",
  Designer: "Designer",
  Security: "Security",
  FileStructurePlanner: "File Structure Planner",
  BackendDeveloper: "Backend Developer",
  FrontendDeveloper: "Frontend Developer",
  QA: "QA",
  Document: "Document",
  DevOps: "DevOps",
  Retro: "Retro",
}

// ---------------------------------------------------------------- Types

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

export interface PipelineStartResult {
  project_id: string
  state: string
  success: boolean
  requires_user_action: boolean
  action_needed?: string
  completed_stages: string[]
  failed_stage: string | null
  message: string
}

export interface WorkflowStatus {
  project_id: string
  state?: string
  current_stage: string | null
  completed_stages: string[]
  failed_stage: string | null
  total_stages: number
  progress_percent: number
  status: "not_started" | "running" | "paused" | "stopped" | "complete" | "failed"
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

export interface DesignApprovalResponse {
  state: string
  iteration?: number
  message: string
  next?: string
}

export interface StageRunResult {
  workflow: {
    id: string
    project_id: string
    current_stage: string
    state: string
    created_at: string
    updated_at: string
  }
  success: boolean
  message: string
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

export interface MemoryRecord {
  key: string
  value_preview: string
  stored_at: string
}

export interface MemorySummary {
  project_id: string
  records: MemoryRecord[]
  lesson_count: number
  trajectory_count: number
  knowledge_entry_count: number
}

export interface PlannedFile {
  path: string
  module: string
  purpose: string
  responsible_stage: string
}

export interface LLMSettings {
  provider: string
  model: string
  base_url: string
  bedrock_region: string
  bedrock_api_key_set: boolean
}

export interface LLMSettingsUpdate {
  provider?: string
  model?: string
  bedrock_api_key?: string
  bedrock_region?: string
}

export interface ProviderInfo {
  id: string
  label: string
  models: string[]
  requires_api_key: boolean
}

// ---------------------------------------------------------------- Calls

export const api = {
  health: () => request<{ status: string }>("/health"),
  ready: () => request<ReadyStatus>("/ready"),

  listProjects: () => request<ProjectSummary[]>("/projects"),
  createProject: (name: string, description: string) =>
    request<CreateProjectResult>("/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  getProject: (projectId: string) => request<ProjectDetail>(`/projects/${projectId}`),
  deleteProject: (projectId: string) => request<void>(`/projects/${projectId}`, { method: "DELETE" }),

  startWorkflow: (projectId: string, requestText: string) =>
    request<PipelineStartResult>("/workflow/start", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, request: requestText }),
    }),
  getWorkflowStatus: (projectId: string) => request<WorkflowStatus>(`/workflow/${projectId}`),
  
  getDesignReview: (projectId: string) => request<DesignReviewData>(`/workflow/${projectId}/design-review`),
  postDesignReview: (projectId: string, approved: boolean, feedback?: string, modified_design?: Record<string, unknown>) =>
    request<DesignApprovalResponse>(`/workflow/${projectId}/design-review`, {
      method: "POST",
      body: JSON.stringify({ approved, feedback, modified_design }),
    }),
  continueWorkflow: (projectId: string) =>
    request<PipelineStartResult>(`/workflow/${projectId}/continue`, { method: "POST" }),

  runStage: (projectId: string, stage: string, requestText: string) =>
    request<StageRunResult>("/workflow/stage", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, stage, request: requestText }),
    }),
  stopWorkflow: (projectId: string) =>
    request<{ project_id: string; stop_requested: boolean }>(`/workflow/${projectId}/stop`, { method: "POST" }),

  getLogs: (projectId: string, sinceId = 0) =>
    request<LogEvent[]>(`/projects/${projectId}/logs?since_id=${sinceId}`),

  getFiles: (projectId: string) => request<ProjectFiles>(`/projects/${projectId}/files`),
  getFileContent: (projectId: string, area: string, path: string) =>
    request<FileContent>(`/projects/${projectId}/files/${area}/${path}`),

  getCost: (projectId: string) => request<CostSummary>(`/projects/${projectId}/cost`),

  getRunInstructions: (projectId: string) =>
    request<{ project_id: string; markdown: string }>(`/projects/${projectId}/run-instructions`),
  downloadUrl: (projectId: string) => `${BASE}/projects/${projectId}/download`,

  listArtifacts: (projectId: string) => request<ArtifactSummary[]>(`/artifacts/${projectId}`),
  getArtifact: (projectId: string, stage: string) => request<ArtifactDetail>(`/artifacts/${projectId}/${stage}`),
  getArtifactHistory: (projectId: string, stage: string) =>
    request<ArtifactHistoryItem[]>(`/artifacts/${projectId}/${stage}/history`),

  listAgents: () => request<AgentInfo[]>("/agents"),
  getMemory: (projectId: string) => request<MemorySummary>(`/memory/${projectId}`),

  getLLMSettings: () => request<LLMSettings>("/settings/llm"),
  updateLLMSettings: (update: LLMSettingsUpdate) =>
    request<LLMSettings>("/settings/llm", { method: "POST", body: JSON.stringify(update) }),
  listProviders: () => request<{ providers: ProviderInfo[] }>("/settings/providers"),
}

