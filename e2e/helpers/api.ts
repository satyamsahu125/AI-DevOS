/**
 * AI DevOS — Direct API helpers for test setup/teardown.
 *
 * Uses the actual API contract discovered in Phase 0:
 * - API base: /api/v1
 * - Auth: not required (AUTH_ENABLED=false by default)
 * - ProjectRequest DTO: { name, description, mode } — NO project_type field
 * - Project status: GET /api/v1/projects/{id} → { project_id, name, status, current_stage, stages_completed }
 *
 * Do NOT call these from the browser context — use APIRequestContext (Playwright's request fixture).
 */
import { APIRequestContext } from '@playwright/test';

export const BASE = process.env.BACKEND_URL || 'http://localhost:8000';
const API = `${BASE}/api/v1`;

// ── Types ──────────────────────────────────────────────────────────────────────

export interface CreateProjectPayload {
  name: string;
  description: string;
  /** "full" (default, all stages) or "quick" (prototype, skips Security/Doc/Retro/HumanGates) */
  mode?: 'full' | 'quick';
}

export interface ProjectStatus {
  project_id: string;
  name: string;
  description: string;
  /** not_started | running | complete | failed | paused | stopped */
  status: string;
  current_stage: string;
  stages_completed: string[];
  artifacts: Array<{ stage: string; file: string; attempt: number }>;
  workspace_path: string;
  clarification_questions?: string[];
  error?: string;
}

export interface ProjectFiles {
  project_id: string;
  project_path: string;
  total_files: number;
  files: Array<{ path: string; size_bytes: number; language: string; sprint: number }>;
  backend: string[];
  frontend: string[];
}

// ── Project lifecycle ──────────────────────────────────────────────────────────

/**
 * Create a project AND start the pipeline in one call.
 * Returns { id, name, description, status, state }.
 *
 * Project type is inferred by the pipeline from the description text.
 * Write descriptions that make the technology stack obvious:
 *   Python/FastAPI → "A FastAPI Python REST API that..."
 *   React Native   → "A React Native mobile app that..."
 */
export async function createProject(
  request: APIRequestContext,
  payload: CreateProjectPayload,
): Promise<{ id: string; name: string; description: string }> {
  const body = {
    name: payload.name,
    description: payload.description,
    mode: payload.mode ?? 'quick',  // default quick so tests complete faster
  };
  const res = await request.post(`${API}/projects/create-and-run`, { data: body });
  if (!res.ok()) {
    throw new Error(`createProject failed: ${res.status()} ${await res.text()}`);
  }
  return res.json();
}

/**
 * Delete a project and its workspace (no-op if already deleted).
 */
export async function deleteProject(
  request: APIRequestContext,
  projectId: string,
): Promise<void> {
  await request.delete(`${API}/projects/${projectId}`);
  // 204 = success, 404 = already deleted — both are fine for cleanup
}

/**
 * Fetch the current project status.
 * Returns the full project detail: status, current_stage, stages_completed, etc.
 */
export async function getProjectStatus(
  request: APIRequestContext,
  projectId: string,
): Promise<ProjectStatus> {
  const res = await request.get(`${API}/projects/${projectId}`);
  if (!res.ok()) {
    throw new Error(`getProjectStatus failed: ${res.status()} for project ${projectId}`);
  }
  return res.json();
}

/**
 * List all files generated in the project workspace.
 */
export async function getProjectFiles(
  request: APIRequestContext,
  projectId: string,
): Promise<ProjectFiles> {
  const res = await request.get(`${API}/projects/${projectId}/files`);
  if (!res.ok()) {
    throw new Error(`getProjectFiles failed: ${res.status()} for project ${projectId}`);
  }
  return res.json();
}

/**
 * Get the content of a single generated file.
 */
export async function getFileContent(
  request: APIRequestContext,
  projectId: string,
  filePath: string,
): Promise<{ content: string; language: string; size: number }> {
  const res = await request.get(`${API}/projects/${projectId}/files/${filePath}`);
  if (!res.ok()) {
    throw new Error(`getFileContent failed: ${res.status()} for ${filePath}`);
  }
  return res.json();
}

/**
 * Get the latest sandbox results for a project.
 * Returns 404 if sandbox has not run yet.
 */
export async function getSandboxResults(
  request: APIRequestContext,
  projectId: string,
): Promise<Record<string, unknown> | null> {
  const res = await request.get(`${API}/projects/${projectId}/sandbox-results`);
  if (res.status() === 404) return null;
  if (!res.ok()) {
    throw new Error(`getSandboxResults failed: ${res.status()} for project ${projectId}`);
  }
  return res.json();
}

/**
 * Get all memory records for a project.
 */
export async function getProjectMemory(
  request: APIRequestContext,
  projectId: string,
): Promise<{ project_id: string; records: Array<{ key: string; value_preview: string }> }> {
  const res = await request.get(`${API}/memory/${projectId}`);
  if (!res.ok()) {
    throw new Error(`getProjectMemory failed: ${res.status()} for project ${projectId}`);
  }
  return res.json();
}

/**
 * Get the current pending gate (if any) for a project.
 * Returns null if no gate is pending.
 */
export async function getCurrentGate(
  request: APIRequestContext,
  projectId: string,
): Promise<{ gate: string | null; state: string; artifact: Record<string, unknown> }> {
  const res = await request.get(`${API}/workflow/${projectId}/gates/current`);
  if (!res.ok()) {
    throw new Error(`getCurrentGate failed: ${res.status()} for project ${projectId}`);
  }
  return res.json();
}

/**
 * Approve a gate by name ('architecture' | 'design' | 'sprint_plan').
 */
export async function approveGate(
  request: APIRequestContext,
  projectId: string,
  gate: 'architecture' | 'design' | 'sprint_plan',
): Promise<void> {
  const gateUrl = gate === 'sprint_plan' ? 'sprint-plan' : gate;
  const res = await request.post(`${API}/workflow/${projectId}/gates/${gateUrl}/approve`);
  if (!res.ok()) {
    // 409 means no gate pending — that's fine when running without human approval
    if (res.status() !== 409) {
      throw new Error(`approveGate(${gate}) failed: ${res.status()} ${await res.text()}`);
    }
  }
}

// ── Polling helpers ─────────────────────────────────────────────────────────────

/**
 * Poll until the named stage appears in stages_completed OR is the current_stage.
 * Throws if the project fails or the timeout is exceeded.
 */
export async function waitForStage(
  request: APIRequestContext,
  projectId: string,
  stage: string,
  timeoutMs = 180_000,
): Promise<ProjectStatus> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await getProjectStatus(request, projectId);
    const stageNameLc = stage.toLowerCase();
    const completedLc = (status.stages_completed ?? []).map(s => s.toLowerCase());
    const currentLc = (status.current_stage ?? '').toLowerCase();

    if (completedLc.some(s => s.includes(stageNameLc)) || currentLc.includes(stageNameLc)) {
      return status;
    }
    if (status.status === 'failed') {
      throw new Error(
        `Project ${projectId} failed at stage '${status.current_stage}'. ` +
        `Completed: [${status.stages_completed.join(', ')}]`,
      );
    }
    if (status.status === 'complete') {
      return status; // pipeline finished before we saw the stage name — that's fine
    }
    await sleep(3000);
  }
  const final = await getProjectStatus(request, projectId);
  throw new Error(
    `Timeout (${timeoutMs}ms) waiting for stage '${stage}'. ` +
    `Current: '${final.current_stage}', Completed: [${final.stages_completed.join(', ')}]`,
  );
}

/**
 * Poll until the project reaches a terminal state (complete or failed).
 */
export async function waitForCompletion(
  request: APIRequestContext,
  projectId: string,
  timeoutMs = 600_000,
): Promise<ProjectStatus> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await getProjectStatus(request, projectId);
    if (status.status === 'complete' || status.status === 'failed') {
      return status;
    }
    await sleep(5000);
  }
  const final = await getProjectStatus(request, projectId);
  throw new Error(
    `Timeout (${timeoutMs}ms) waiting for project ${projectId} to complete. ` +
    `Status: ${final.status}, Stage: ${final.current_stage}`,
  );
}

// ── Utilities ──────────────────────────────────────────────────────────────────

export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
