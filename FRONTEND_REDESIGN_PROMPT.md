# AI DevOS — Frontend Redesign Brief
# Feed this entire file to your chosen AI designer to rebuild the frontend.

---

## WHAT IS AI DEVOS

AI DevOS is an autonomous software engineering platform. Users describe a software
project in plain English. A pipeline of AI agents builds it — planning, designing,
writing code, running QA, deploying — without human involvement except at key approval gates.

Think of it as: "ChatGPT for building full software products."

The UI needs to feel like a mission control / IDE hybrid. Dark theme. Minimal.
Professional. Every element should communicate "AI is working hard on your behalf."

---

## TECH STACK (do not change)

- React + TypeScript
- Vite dev server (proxies /api → localhost:8000)
- React Router v6
- Tailwind CSS
- WebSocket for live updates

---

## ROUTES (2 pages only)

```
/             → redirect to /projects
/projects     → Dashboard: list all projects, create new ones
/projects/:projectId  → Workspace: full IDE-like view for one project
```

---

## BACKEND API — ALL ENDPOINTS

Base URL: `/api` (proxied by Vite)

### Health
```
GET  /health           → { status: string }
GET  /ready            → { status, ollama, model, model_available, database, timestamp }
```

### Projects
```
GET    /projects              → ProjectSummary[]
POST   /projects              → body: { name, description } → CreateProjectResult
GET    /projects/:id          → ProjectDetail
DELETE /projects/:id          → 204
```

### Workflow (core pipeline control)
```
POST   /workflow/start             → body: { project_id, request } → starts the AI pipeline
GET    /workflow/:id               → WorkflowStatus (poll this for pipeline state)
POST   /workflow/:id/stop          → stops the pipeline
POST   /workflow/:id/continue      → resumes a paused pipeline
POST   /workflow/stage             → body: { project_id, stage, request } → runs one specific stage
```

### Design Review (human approval gate)
```
GET    /workflow/:id/design-review → DesignReviewData (the AI's design proposal)
POST   /workflow/:id/design-review → body: { approved: bool, feedback?: string, modified_design?: object }
                                   → user approves or requests revisions
```

### Q&A Session (clarification before pipeline starts)
```
GET    /workflow/:id/qa            → QASession (current question + history)
POST   /workflow/:id/qa/answer     → body: { question_index, answer }
POST   /workflow/:id/qa/skip       → body: { question_index }
POST   /workflow/:id/qa/complete   → marks Q&A done, pipeline proceeds
```

### Requirement Changes (mid-pipeline change requests)
```
POST   /workflow/:id/change         → body: { description }
POST   /workflow/:id/change/confirm → body: { change_id, confirmed, comment }
POST   /workflow/:id/change/cancel  → body: { change_id }
GET    /workflow/:id/changes        → { changes: [] }
```

### Logs
```
GET    /projects/:id/logs?since_id=N → LogEvent[] (poll with since_id for incremental)
```

### Files
```
GET    /projects/:id/files               → { backend: string[], frontend: string[] }
GET    /projects/:id/files/:area/:path   → FileContent
GET    /projects/:id/run-instructions    → { markdown: string }
GET    /projects/:id/download            → ZIP download of entire project
```

### Artifacts (AI agent outputs)
```
GET    /artifacts/:id              → ArtifactSummary[]
GET    /artifacts/:id/:stage       → ArtifactDetail
GET    /artifacts/:id/:stage/history → ArtifactHistoryItem[]
```

### Metrics & Memory
```
GET    /projects/:id/cost     → CostSummary (token usage, latency)
GET    /projects/:id/metrics  → performance data
GET    /memory/:id            → MemorySummary (what agents have learned)
GET    /learning/performance/:stage → PerformanceData
GET    /learning/patterns     → { patterns: [] }
```

### Agents & Settings
```
GET    /agents               → AgentInfo[] (all registered agents)
GET    /settings/llm         → LLMSettings
POST   /settings/llm         → update LLM provider/model
GET    /settings/providers   → { providers: ProviderInfo[] }
```

### Chat
```
POST   /projects/:id/chat    → body: { message } → { reply, action_taken?, stage_triggered? }
```

---

## KEY DATA SHAPES

```typescript
// Pipeline state — what the WorkflowStatus endpoint returns
WorkflowStatus = {
  project_id: string
  state: string          // "empty" | "clarifying" | "requirements_ready" | "architecture_ready"
                         // | "design_ready" | "design_review_pending" | "design_approved"
                         // | "sprint_plan_ready" | "sprint_in_progress" | "all_sprints_complete"
                         // | "complete" | "failed" | "sprint_blocked"
  status: "not_started" | "running" | "paused" | "stopped" | "complete" | "failed"
  current_stage: string | null
  completed_stages: string[]
  failed_stage: string | null
  progress_percent: number       // 0–100
  requires_user_action: boolean  // show approval button when true
  current_sprint: number
  total_sprints: number
  sprint_name: string
  sprint_progress: string        // e.g. "Sprint 2 of 4"
}

// The 12 pipeline stages (in order)
STAGES = [
  "StrategicReview",    // Business analysis & Q&A
  "ProductOwner",       // User stories & acceptance criteria
  "Architect",          // System design, API contracts, DB schema
  "Designer",           // UI wireframes, component map  ← USER APPROVES HERE
  "Security",           // Threat model, security rules
  "FileStructurePlanner", // File structure plan
  "BackendDeveloper",   // Backend code
  "FrontendDeveloper",  // Frontend code
  "QA",                 // Tests & QA report
  "Document",           // Docs & API reference
  "DevOps",             // Deployment manifest
  "Retro",              // Project retrospective
]

// WebSocket message types (ws://localhost:8000/ws/:projectId)
WS_EVENTS = [
  "status_update"    // pipeline state changed
  "stage_started"    // agent began working
  "stage_complete"   // agent finished (includes duration_seconds)
  "stage_retry"      // agent retrying (includes attempt number + feedback)
  "stage_failed"     // agent failed permanently
  "log_line"         // freeform log message
  "file_added"       // a new source file was written
  "qa_question"      // Q&A: new question ready
  "approval_needed"  // waiting for design review
  "pipeline_done"    // entire pipeline complete
]

QASession = {
  status: "pending" | "in_progress" | "complete"
  total_questions: number
  answered: number
  current_question_index: number
  current_question: {
    index: number
    question: string
    category: string      // "business" | "technical" | "design" | etc.
    priority: "required" | "optional"
    options: { value: string; label: string }[] | null   // null = free text
    allows_custom: boolean
    skippable: boolean
  }
  previous_answers: { question_index, question, answer }[]
  is_complete: boolean
}

LogEvent = {
  id: number
  stage: string
  level: "info" | "warning" | "error"
  message: string
  created_at: string
}

CostSummary = {
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  total_latency_ms: number
}

MemorySummary = {
  records: { key: string; value_preview: string; stored_at: string }[]
  lesson_count: number
  trajectory_count: number
  knowledge_entry_count: number
}
```

---

## PAGE 1: /projects — Dashboard

### Purpose
Landing page. See all projects at a glance, create new ones, check system health.

### Must have
- Header bar: "AI DevOS" logo/wordmark + system health indicator (green dot if /ready is OK)
- LLM settings button (opens modal to change provider/model — GET/POST /settings/llm)
- Grid of project cards, each showing:
  - Project name
  - Status badge (color-coded: running=blue pulse, complete=green, failed=red, paused=amber)
  - Current stage or last completed stage
  - Created date
  - Click → navigate to /projects/:id
- "New Project" button → modal with:
  - Name field (required)
  - Description textarea (what do you want to build?)
  - Submit → POST /projects → navigate to the new project
- Empty state when no projects exist
- Delete project (with confirmation)

### Visual direction
Dark background (#09090b zinc-950). Cards with subtle border glow on hover.
Status badges as colored pills. Animated pulse on running projects.
The create modal should feel premium — centered, glassmorphism blur backdrop.

---

## PAGE 2: /projects/:projectId — Workspace

### Purpose
Full mission-control view. User watches AI build their project in real time.
Divided into two zones: left (main context) and right (workbench/tools).

### Top bar (always visible)
- Back arrow → /projects
- Project name
- Status chip (running / paused / complete / failed)
- WebSocket live indicator (green "Live" or "Polling")
- Action buttons (context-sensitive — only one visible at a time):
  - "▶ Start Build" → POST /workflow/start (when not_started or stopped)
  - "■ Stop" → POST /workflow/:id/stop (when running)
  - "▶ Continue" → POST /workflow/:id/continue (when paused)
- "⚡ Review Design" button → appears + pulses when requires_user_action=true
- "⬇ Download" → links to /api/projects/:id/download

### Stage Rail (below top bar, always visible)
Horizontal progress rail showing all 12 stages.
Each stage is a node: pending (grey) / active (blue pulse) / complete (green check) / failed (red X).
Clicking a completed stage opens its artifact.
Sprint progress bar appears below rail when sprints are active:
  "Sprint 2 of 4 ████████░░░░ User Auth Sprint"

### Left panel — context (switches based on pipeline state)

**State: empty / not started**
  - Hero empty state: "Ready to build" message, prominent Start button

**State: clarifying / qa_pending / qa_in_progress**  
  - Q&A Panel:
    - Progress bar (X of Y questions answered)
    - Current question prominently displayed with category badge
    - If question has options: radio/button group
    - Free text input below (always shown if allows_custom=true)
    - Skip button (if skippable=true)
    - Previous answers list (collapsible)
    - "Complete Q&A" button when all required questions answered

**State: clarifying + status=paused (pipeline initialising)**
  - Initialising panel: clock icon, "Pipeline initialising" message, inline Continue button

**State: design_review_pending**
  - Design Review modal (fullscreen overlay):
    - Shows the AI's design proposal (architecture, wireframes, component map)
    - "Approve" button → POST design-review with approved=true
    - "Request Changes" with feedback textarea → POST with approved=false + feedback
    - Iteration counter ("Review #2")

**All other states (running, complete, failed, sprints)**
  - Chat/Activity Panel:
    - Live log stream (WebSocket events rendered as activity feed)
    - Each log line styled by type: stage_started (blue), stage_complete (green),
      stage_retry (amber), stage_failed (red), file_added (purple), log_line (grey)
    - "Request Change" input at bottom → POST /workflow/:id/change
    - If failed: show failed stage + "Retry Stage" button

### Right panel — workbench tabs (420px fixed width)

**📋 Logs tab**
  - Scrollable log list from GET /projects/:id/logs (poll every 3s)
  - Filter by level (info/warning/error)
  - Auto-scroll to bottom, with "scroll paused" indicator when user scrolls up
  - Timestamps, color-coded levels

**📁 Files tab**
  - Tree view of backend/ and frontend/ directories
  - GET /projects/:id/files for structure
  - Click file → GET /projects/:id/files/:area/:path → show code with syntax highlighting
  - Language detection from file extension
  - "Run Instructions" button → GET /projects/:id/run-instructions → markdown modal

**📦 Artifacts tab**
  - List of completed stages with their artifact
  - GET /artifacts/:id for list, GET /artifacts/:id/:stage for content
  - Click artifact → modal with markdown-rendered content
  - Show attempt number (e.g. "Attempt 2") and version history button
  - Tabs within artifact: "Content" | "History" | "Structured"

**📊 Metrics tab**
  - Token usage: prompt / completion / total (GET /projects/:id/cost)
  - Latency breakdown per stage
  - Memory summary: lessons learned, trajectories (GET /memory/:id)
  - Agent registry (GET /agents) — table of all 19 agents, their status

---

## REAL-TIME BEHAVIOR (WebSocket)

Connect to: `ws://localhost:8000/ws/:projectId`

Reconnect automatically on disconnect (exponential backoff, max 30s).
Show "Live" indicator when connected, "Polling" when falling back to HTTP.

On connection failure: fall back to polling GET /workflow/:id every 5 seconds.

Handle these WebSocket message types and update UI accordingly:
- `stage_started` → mark stage as active in rail, add log entry
- `stage_complete` → mark stage green in rail, add log entry with duration
- `stage_retry` → add amber log entry with attempt number
- `stage_failed` → mark stage red, show failure UI
- `log_line` → append to live log stream
- `file_added` → append file path to live log stream, refresh file tree
- `qa_question` → switch left panel to Q&A panel
- `approval_needed` → show ⚡ Review Design button pulsing
- `pipeline_done` → show success state, confetti optional

---

## VISUAL DESIGN DIRECTION

**Color palette (Tailwind)**
- Background: zinc-950 (#09090b)
- Surface: zinc-900 (#18181b)
- Border: zinc-800 (#27272a)
- Text primary: zinc-100
- Text secondary: zinc-400
- Text muted: zinc-600
- Accent: indigo-500/600 (primary actions, active states)
- Success: emerald-400/500
- Warning: amber-400/500
- Error: rose-400/500
- Sprint/info: indigo-400

**Typography**
- Font: Inter or Geist (system-ui fallback)
- Monospace: JetBrains Mono or Fira Code (for logs, code, artifacts)

**Components feel**
- Borders: subtle (zinc-800/60 at 60% opacity)
- Shadows: minimal — use border glow instead
- Radius: rounded-lg (8px) for cards, rounded-xl (12px) for modals
- Animations: subtle — 150ms transitions, pulse only on genuinely active states
- No gradients except for very subtle header backgrounds
- Icons: Heroicons or Lucide (already in project)

**Stage rail nodes**
- Pending: zinc-800 circle, no fill
- Active: indigo-500 circle, subtle outer ring pulse animation
- Complete: emerald-500 circle with checkmark
- Failed: rose-500 circle with X
- Connect with thin zinc-700 line between nodes

**Log stream line styling**
- stage_started: `▶ Architect started` — indigo-400
- stage_complete: `✓ Architect done (12s)` — emerald-400
- stage_retry: `↩ Architect retry 2` — amber-400
- stage_failed: `✗ Architect failed` — rose-400
- file_added: `📄 backend/app/auth.py` — violet-400
- log_line: plain zinc-400

---

## STATE MACHINE (how pipeline state maps to UI)

```
empty              → Show "Start Build" button, empty state panel
clarifying         → Q&A panel (if running) or "initialising" panel (if paused)
qa_pending         → Q&A panel
qa_in_progress     → Q&A panel
requirements_ready → Stage rail shows StrategicReview + ProductOwner complete
architecture_ready → Stage rail shows + Architect complete
design_ready       → Stage rail shows + Designer complete
design_review_pending → Show ⚡ Review Design, open modal
design_approved    → Continue button (pipeline ready to proceed)
sprint_plan_ready  → Show sprint progress bar
sprint_in_progress → Show sprint progress, current agent pulsing
all_sprints_complete → Sprints done, release phase starting
complete           → Success state, download button prominent
failed             → Error state, show failed stage, retry option
sprint_blocked     → Warning state: "Sprint blocked — retry limit exceeded, needs review"
```

---

## INTERACTIONS THAT MUST WORK

1. Create project → modal → submit → navigate to workspace → Start Build → watch pipeline
2. Q&A flow: answer questions → complete → pipeline resumes automatically
3. Design review: AI proposes design → user approves → sprints begin
4. Stop → pipeline stops → Continue → resumes from where it stopped
5. Live log stream updates as agents run (WebSocket)
6. Stage rail updates in real time as stages complete
7. Click completed stage in rail → open its artifact
8. File explorer: browse generated code files
9. Metrics tab: see token usage grow in real time
10. Download button: GET /api/projects/:id/download → ZIP file

---

## WHAT NOT TO BUILD

- No user authentication (no login page)
- No settings page (LLM settings are a modal on the dashboard)
- No dark/light toggle (always dark)
- No i18n
- No mobile layout needed (desktop-only, min-width 1200px)

---

## FILE STRUCTURE TO PRODUCE

```
frontend/src/
  main.tsx               (entry point — don't change)
  App.tsx                (router — 2 routes only)
  lib/
    api.ts               (all API calls — use the exact shapes above)
  hooks/
    usePipeline.ts       (WebSocket + polling + PipelineState)
    useWebSocket.ts      (raw WS connection with reconnect)
    useLogs.ts           (log polling hook)
  pages/
    ProjectsPage.tsx
    WorkspacePage.tsx
  components/
    ui/
      Spinner.tsx
      Badge.tsx
      Modal.tsx
    pipeline/
      StageRail.tsx
    qa/
      QAPanel.tsx
    design/
      DesignReviewModal.tsx
    chat/
      ChatPanel.tsx        (live log stream + change request)
    files/
      FileExplorer.tsx
    logview/
      LogsPanel.tsx
    artifacts/
      ArtifactsPanel.tsx
    metrics/
      MetricsPanel.tsx
```

---

## REFERENCE: what the current UI does (to improve on)

The current UI is functional but plain. Key improvements needed:
- Dashboard: projects are in a flat list — make it a grid of cards
- Stage rail: circles are plain — add connectors, labels, tooltips
- Log stream: unformatted text — color-code by type with icons
- Q&A panel: basic inputs — make it feel like a chat interview
- Artifact viewer: raw text — render markdown, add syntax highlighting
- Metrics: numbers only — add charts (token usage over time, latency bars)
- Empty state: minimal — make it feel welcoming and explain what AI DevOS does

The redesign should feel like: Linear meets Vercel meets an AI lab dashboard.
Not over-designed. Not a toy. A tool professionals would use daily.
