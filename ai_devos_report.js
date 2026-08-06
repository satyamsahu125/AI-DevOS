const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, PageBreak, NumberingFormat, LevelFormat } = require('docx');
const fs = require('fs');

function h1(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 400, after: 200 } });
}
function h2(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 150 } });
}
function h3(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 100 } });
}
function p(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, size: 22, ...opts })],
    spacing: { before: 100, after: 100 },
  });
}
function bold(text) {
  return new Paragraph({ children: [new TextRun({ text, bold: true, size: 22 })], spacing: { before: 100, after: 50 } });
}
function bullet(text, level = 0) {
  return new Paragraph({
    text,
    bullet: { level },
    spacing: { before: 60, after: 60 },
  });
}
function code(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: 'Courier New', size: 18, color: '1a1a2e' })],
    spacing: { before: 80, after: 80 },
    indent: { left: 720 },
  });
}
function divider() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'cccccc', space: 1 } },
    spacing: { before: 200, after: 200 },
  });
}
function severityRow(sev, label, bg) {
  return new TableRow({
    children: [
      new TableCell({
        children: [new Paragraph({ children: [new TextRun({ text: sev, bold: true, color: 'ffffff', size: 20 })], alignment: AlignmentType.CENTER })],
        shading: { type: ShadingType.CLEAR, fill: bg },
        width: { size: 1800, type: WidthType.DXA },
      }),
      new TableCell({
        children: [new Paragraph({ children: [new TextRun({ text: label, size: 20 })], spacing: { before: 80, after: 80 } })],
        width: { size: 7200, type: WidthType.DXA },
      }),
    ],
  });
}

function issueBlock(id, severity, title, location, description, impact, recommendation) {
  const sevColors = { CRITICAL: 'C0392B', HIGH: 'E67E22', MEDIUM: '2980B9', LOW: '27AE60', INFO: '7F8C8D' };
  const color = sevColors[severity] || '7F8C8D';
  return [
    new Paragraph({
      children: [
        new TextRun({ text: `[${id}] `, bold: true, size: 22, color }),
        new TextRun({ text: title, bold: true, size: 22 }),
        new TextRun({ text: `  `, size: 22 }),
        new TextRun({ text: severity, bold: true, size: 18, color: 'ffffff', highlight: severity === 'CRITICAL' ? 'red' : severity === 'HIGH' ? 'yellow' : 'cyan' }),
      ],
      spacing: { before: 220, after: 80 },
    }),
    new Paragraph({ children: [new TextRun({ text: '📁 Location: ', bold: true, size: 20 }), new TextRun({ text: location, size: 20, font: 'Courier New' })], spacing: { before: 60, after: 60 } }),
    new Paragraph({ children: [new TextRun({ text: 'Description: ', bold: true, size: 20 }), new TextRun({ text: description, size: 20 })], spacing: { before: 60, after: 60 } }),
    new Paragraph({ children: [new TextRun({ text: 'Impact: ', bold: true, size: 20, color: 'C0392B' }), new TextRun({ text: impact, size: 20 })], spacing: { before: 60, after: 60 } }),
    new Paragraph({ children: [new TextRun({ text: 'Fix: ', bold: true, size: 20, color: '27AE60' }), new TextRun({ text: recommendation, size: 20 })], spacing: { before: 60, after: 120 } }),
  ];
}

const doc = new Document({
  numbering: { config: [] },
  sections: [{
    properties: {},
    children: [
      // ── TITLE ──
      new Paragraph({
        children: [new TextRun({ text: 'AI DevOS — Full Codebase Analysis Report', bold: true, size: 52 })],
        alignment: AlignmentType.CENTER, spacing: { before: 600, after: 200 },
      }),
      new Paragraph({
        children: [new TextRun({ text: 'Prepared: 2026-08-01  |  Scope: Complete Backend + Frontend Pipeline Audit', size: 22, color: '666666' })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 600 },
      }),
      divider(),

      // ── EXECUTIVE SUMMARY ──
      h1('1. Executive Summary'),
      p('AI DevOS is an ambitious autonomous software-engineering platform that orchestrates a multi-agent pipeline (Strategic Review → Product Owner → Architect → Designer → Security → Sprint Planning → Sprints → QA → DevOps → Documentation → Retro) backed by local Ollama or cloud LLM providers (Claude, Gemini, Bedrock).'),
      p('The architecture is well-structured with clear separation of concerns: a Workflow Engine drives execution, a Reviewer gates every stage, a MemoryManager provides project-scoped persistence, and an EventBroadcaster pushes live progress over WebSockets. The frontend is a clean React/Vite/Tailwind SPA.'),
      p('However, a deep read of the source reveals several serious defects that prevent the system from working reliably end-to-end. The most critical are a dual-container boot that creates two independent dependency graphs (the API routes use one, the kernel lifecycle manages the other), a broken WebSocket broadcast path from inside LLM calls, a model mismatch between .env and the startup script, and agents that bypass DI and create unbounded LLMManager instances. These must be resolved before the platform can be trusted in production or even a stable demo.'),
      divider(),

      // ── SYSTEM OVERVIEW ──
      h1('2. System Architecture Overview'),
      h2('2.1 Technology Stack'),
      bullet('Backend: Python 3.12+, FastAPI, Uvicorn, Pydantic v2, SQLite (5 databases), hnswlib (vector index)'),
      bullet('LLM Providers: Ollama (local), Anthropic Claude API, Google Gemini API, AWS Bedrock'),
      bullet('Frontend: React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Radix UI, Framer Motion'),
      bullet('Agent Pipeline: 11+ named stages + sprint-internal sub-stages'),
      bullet('Memory: SQLite-backed MemoryManager (key-value), KnowledgeMemory (vector), LearningLoop, LessonStore'),
      bullet('Transport: REST API + WebSocket per project_id for real-time pipeline events'),

      h2('2.2 Pipeline Execution Flow'),
      p('Request → POST /workflow/start → BackgroundTask → WorkflowManager.run() → PipelineSupervisor → [Discovery Stages] → [Sprint Loop] → [Release Stages] → Done'),
      p('Each stage: WorkflowEngine.run() → ExecutionManager → ExecutionPipeline → AgentFactory.create() → agent.execute() → ArtifactManager.save() → Reviewer.review() → [approve / retry / exhaust]'),

      h2('2.3 Directory Layout'),
      bullet('backend/app/agents/          — 25+ agent implementations + factory/registry'),
      bullet('backend/app/actions/         — LLM-backed action classes (one per stage)'),
      bullet('backend/app/workflow/        — Engine, Manager, PipelineSupervisor, StateMachine'),
      bullet('backend/app/memory/          — MemoryManager, LearningLoop, LessonStore, KnowledgeMemory'),
      bullet('backend/app/execution/       — ExecutionEngine, ExecutionPipeline, SafetyPolicy'),
      bullet('backend/app/llm/             — LLMManager, LLMFactory, 4 providers'),
      bullet('backend/app/api/             — FastAPI routers (14 modules) + WebSocket'),
      bullet('backend/app/kernel/          — Container (DI wiring), Bootstrap, AIKernel'),
      bullet('frontend/src/               — React SPA: pages, hooks, components, lib/api.ts'),
      divider(),

      // ── CRITICAL BUGS ──
      h1('3. Critical Bugs & Errors'),
      p('The following defects are confirmed by static analysis. They cause functional failures or data corruption under normal operation.'),

      ...issueBlock('B-01', 'CRITICAL', 'Dual Container Instantiation — API and Kernel use separate DI trees',
        'app/main.py:12  +  app/api/dependencies.py:21',
        'main.py creates AIKernel() → Bootstrap() → Container().build() (kernel container). Then api/dependencies.py creates a second Container().build() (API container) at module load time. FastAPI route handlers use Depends(get_container) which returns the API container — a completely separate object. The kernel container\'s services (workflow_engine, memory_manager, etc.) are never used by any route. AIKernel.start() initialises and lifecycle-manages the kernel container; AIKernel.stop() tears it down. The API container has its own separate singletons that are never stopped.',
        'Two WorkflowManagers, two MemoryManagers, two sets of SQLite connections exist simultaneously. The kernel container\'s shutdown logic (if any) never runs for the services actually serving requests. State written via the kernel path is invisible to the API path and vice versa.',
        'Remove the AIKernel/Bootstrap entirely OR make api/dependencies.py import and reuse the kernel container. The simplest fix: in dependencies.py, import the kernel instance from main.py and return kernel.container from get_container().'),

      ...issueBlock('B-02', 'CRITICAL', 'LLM Progress WebSocket Messages Silently Dropped in Background Threads',
        'app/llm/manager.py  →  app/api/websocket.py::ConnectionManager.broadcast_sync()',
        'LLMManager.generate_text() calls ws_manager.broadcast_sync() to emit "Agent is thinking..." messages. broadcast_sync() calls asyncio.get_running_loop() — but the pipeline runs in a FastAPI BackgroundTask thread (a threadpool thread with NO asyncio loop). get_running_loop() raises RuntimeError in that thread, which broadcast_sync catches and logs as an error, then drops the message. The EventBroadcaster singleton (events/broadcaster.py) solves this correctly using a pre-bound loop via bind_loop(), but LLMManager bypasses EventBroadcaster entirely.',
        'Every "Agent is thinking..." / "Agent has received a response" log line emitted by the LLM layer is silently dropped. The user sees no activity feedback during the longest phase of execution.',
        'Replace ws_manager.broadcast_sync() calls in LLMManager with self.broadcaster (inject EventBroadcaster via DI, or import the singleton). EventBroadcaster._send() uses loop.call_soon_threadsafe() which works from any thread. This also removes the API-layer import from the LLM layer, fixing the layering violation.'),

      ...issueBlock('B-03', 'CRITICAL', 'AgentFactory Bypasses DI — Each Agent Gets Its Own LLMManager Instance',
        'app/agents/factory.py:90  →  app/agents/base_agent.py:__init__',
        'AgentFactory.create() calls implementation() (no arguments). BaseAgent.__init__ defaults llm_manager to LLMManager() when not provided. So every stage execution creates a fresh LLMManager(), which calls ConfigurationManager().load() again from scratch. The DI-registered llm_manager singleton in Container is never passed to any agent created through AgentFactory.',
        'N LLMManager instances are created per pipeline run (one per stage). Each re-reads config.yaml from disk. Cost tracking is scattered: each instance has its own CostTracker that cannot be reconciled. If the user calls /settings to change the provider at runtime, in-flight agents ignore the change.',
        'AgentFactory.create() must accept and forward the DI-wired llm_manager. Either: (a) inject llm_manager into AgentFactory via the Container and forward it to implementation(llm_manager=self._llm_manager), or (b) make agents resolve LLMManager from a shared factory/registry rather than constructing it inline.'),

      ...issueBlock('B-04', 'HIGH', 'Model Mismatch Between .env and run.sh Startup Check',
        'backend/.env  vs  run.sh',
        'backend/.env sets LLM_MODEL=qwen3:8b. run.sh checks for and pulls qwen2.5-coder:7b. ConfigurationLoader applies env vars as overrides with higher priority than config.yaml, so the running server uses qwen3:8b. But the startup script only pulls qwen2.5-coder:7b, so if qwen3:8b is not already present in Ollama, every LLM call fails with a model-not-found error immediately after a seemingly clean startup.',
        'The system appears to start successfully (Ollama health check passes, model check passes for qwen2.5-coder:7b) but the first pipeline execution fails at the first agent call.',
        'Sync run.sh to check/pull the model actually configured in .env. Better: read the model name from the env var in the bash check: MODEL="${LLM_MODEL:-qwen2.5-coder:7b}".'),

      ...issueBlock('B-05', 'HIGH', 'env MEMORY_DB_PATH vs MEMORY_DB Key Name Mismatch',
        '.env.example  vs  app/memory/manager.py:29',
        '.env.example documents MEMORY_DB_PATH=backend/app/memory/memory.db, but MemoryManager reads os.getenv("MEMORY_DB", "data/memory.sqlite"). The key name differs. Anyone following .env.example sets MEMORY_DB_PATH, which MemoryManager never reads, so the default "data/memory.sqlite" is used instead.',
        'Projects created following the documented setup write memory to an unexpected path. If the user then sets MEMORY_DB_PATH expecting it to be honoured, memory is silently split across two files with no warning.',
        '.env.example must use MEMORY_DB=... to match what MemoryManager actually reads. Alternatively add os.getenv("MEMORY_DB_PATH") as a fallback with a deprecation log.'),

      ...issueBlock('B-06', 'HIGH', 'Duplicate SQLite Database Files in Two Locations',
        'data/*.sqlite  vs  backend/data/*.sqlite',
        'Both /data/ (project root) and /backend/data/ contain memory.sqlite, knowledge.sqlite, learning.sqlite, lessons.sqlite. The active database depends on the current working directory when the server starts: running "uvicorn app.main:app" from /backend/ uses backend/data/, running from root uses data/. The .env sets MEMORY_DB=data/memory.sqlite (relative path). If the server is ever started from a different directory the paths resolve differently.',
        'Data is silently split between two databases. A project run from one working directory is invisible when started from another. The duplicates also waste disk and cause confusion about which file is the source of truth.',
        'Pin all database paths to absolute paths resolved at startup (e.g., Path(__file__).resolve().parents[N] / "data" / "memory.sqlite"). Remove the duplicate root-level data/ directory or add it to .gitignore.'),

      divider(),

      // ── HIGH SEVERITY ISSUES ──
      h1('4. High-Severity Architectural Flaws'),

      ...issueBlock('A-01', 'HIGH', 'Synchronous Pipeline Blocks Threadpool Thread for Entire Run Duration',
        'app/api/workflow.py  →  FastAPI BackgroundTasks',
        'WorkflowManager.run() is a synchronous function. FastAPI\'s BackgroundTasks runs sync tasks in a default threadpool (starlette\'s AnyIO threadpool, default ~40 threads). A full pipeline run can take 30–120+ minutes for a complex project on local hardware. Each concurrent project holds one threadpool thread for the entire duration. With 40 threads max and multi-minute blocking calls, even a modest load of concurrent projects exhausts the pool and hangs all background tasks including unrelated ones.',
        'New projects submitted while the pool is exhausted silently queue and do not start. There is no per-project timeout or preemption — only the cooperative is_stop_requested() check inside the engine loop.',
        'Rewrite the pipeline as a proper async generator with asyncio.to_thread() for LLM calls, or run each project pipeline in a dedicated thread with a thread-per-project model and a bounded executor. At minimum, document the concurrency limit and expose a queue depth metric.'),

      ...issueBlock('A-02', 'HIGH', 'LLMManager Imports from API Layer — Layering Violation',
        'app/llm/manager.py:16  →  from ..api.websocket import ws_manager',
        'LLMManager (core domain layer) directly imports ws_manager from app/api/websocket.py (API layer). This creates a hard dependency from core to the HTTP transport layer. It prevents testing LLMManager without an ASGI app context and breaks the clean layering that the rest of the architecture maintains.',
        'Any test or standalone script that imports LLMManager will transitively import FastAPI and the entire ASGI stack. This is also the root cause of the broadcast_sync thread-safety bug (B-02).',
        'Inject an optional broadcaster callback into LLMManager (or accept an EventBroadcaster). The API layer passes the broadcaster at construction; standalone/test usage passes None.'),

      ...issueBlock('A-03', 'HIGH', 'Sprint Internal Stages Invisible in Frontend and workflow.json',
        'frontend/src/lib/api.ts  +  app/workflow/workflow.json',
        'workflow.json lists 11 top-level stages but omits ScrumMaster, FileStructurePlanner, BackendDeveloper, FrontendDeveloper, TechLead, BugAnalyst, SprintDeploy, SprintReview — all sprint-internal stages. The frontend STAGES constant hardcodes the same 11 stages. During sprint execution (the longest and most important phase), the pipeline sidebar shows no active stage, the live log shows file_added events but no stage_started/stage_complete events for backend or frontend agents, and progress_percent does not advance.',
        'Users see a frozen UI during sprint execution with no feedback about what is happening. This is the worst UX failure during the most critical phase.',
        'Add sprint-internal stages to workflow.json (marked as sprint_scope: true). Update the frontend STAGES constant or make it dynamic. Emit stage_started/stage_complete WebSocket events from within _run_sprint() for each sub-stage. Update progress_percent calculation to include sprint stages.'),

      ...issueBlock('A-04', 'HIGH', 'SprintRetryConfig Settings Fields Are Dead Code',
        'app/config/models.py:SprintRetryConfig  +  grep across entire codebase',
        'Settings.sprint_retry: SprintRetryConfig defines max_dev_review_iterations, max_qa_iterations, and max_spec_fix_iterations. These are documented in the model and appear to be the intended retry control knobs for the sprint feedback loop. However, no code in the entire backend reads these values. WorkflowManager._run_sprint_with_retry() hardcodes max_attempts=2. The settings fields are effectively dead.',
        'Operators cannot tune sprint retry behaviour through configuration. A user who sets MAX_DEV_REVIEW_ITERATIONS=5 in .env gets no effect.',
        'Wire SprintRetryConfig values: pass self._settings.sprint_retry.max_dev_review_iterations to _run_sprint_with_retry(). Add env-var overrides to ConfigurationLoader for the new keys.'),

      ...issueBlock('A-05', 'MEDIUM', 'PipelineSupervisor get_discovery_stages() Splits on Hardcoded Name',
        'app/workflow/pipeline_supervisor.py:get_discovery_stages()',
        'get_discovery_stages() iterates STAGE_ORDER and breaks when it sees "sprint_planner". If workflow.json is reordered or sprint_planner is renamed, the split silently misclassifies stages. The function also calls DependencyGraph._load_config() (a class-level lazy load) on every invocation with no caching guard beyond STAGE_ORDER being non-empty.',
        'Adding a stage before sprint_planner accidentally promotes it to a sprint stage. Renaming sprint_planner breaks the discovery/release split entirely with no error.',
        'Introduce a stage_phase: "discovery"|"sprint"|"release" field in workflow.json and read it directly rather than splitting on name.'),

      divider(),

      // ── MEDIUM ISSUES ──
      h1('5. Medium-Severity Issues'),

      ...issueBlock('M-01', 'MEDIUM', 'WebSocket Ping-Pong Protocol Reversed on Client',
        'frontend/src/hooks/useWebSocket.ts:onmessage handler',
        'The server emits {"type":"ping"} as a keepalive (asyncio.TimeoutError path). The client receives it and responds {"type":"ping"} (another ping). The server\'s message handler then receives the client ping and responds {"type":"pong"}. The client has no pong handler. The protocol works but is semantically backwards: the standard is server sends ping → client responds pong.',
        'Not a functional failure today, but if the server ever adds rate-limiting on back-to-back pings or if the behaviour is changed to match the standard, the handshake will break silently.',
        'Change useWebSocket.ts: if (msg.type === "ping") { ws.send(JSON.stringify({ type: "pong" })); return }'),

      ...issueBlock('M-02', 'MEDIUM', 'ConfigurationManager Re-reads Disk on Every New Instance',
        'WorkflowEngine.__init__:  ConfigurationManager().load()  +  WorkflowManager.__init__',
        'Both WorkflowEngine and WorkflowManager instantiate a new ConfigurationManager() and call .load() in their constructors. Container.build() also creates ConfigurationManager()._settings. Three separate Settings objects exist in memory, each read from disk at construction time. Runtime reconfiguration (POST /settings) updates the API container\'s LLMManager but not the one embedded in WorkflowEngine.',
        'Settings changes at runtime are partially visible: the API-layer LLMManager sees them, but WorkflowEngine._llm_model (set at init) does not update, so log messages report the wrong model name.',
        'Inject the single ConfigurationManager singleton from Container into WorkflowEngine and WorkflowManager rather than having them construct their own.'),

      ...issueBlock('M-03', 'MEDIUM', 'MemoryOrchestrator Registered But Permanently Broken',
        'app/kernel/container.py:91  +  app/memory/memory_manager.py',
        'MemoryOrchestrator is registered as a DI singleton and instantiated with MemoryRepository(storage=None). If any code ever resolves "memory_orchestrator" and calls any method that hits self.repository (store, retrieve, initialize), it will crash with AttributeError because storage=None. The container comment even says "not called anywhere in the live pipeline."',
        'Any future code path that resolves memory_orchestrator will get a silently broken object. It wastes DI slot and memory.',
        'Either remove MemoryOrchestrator from the container entirely, or complete its implementation with a real storage adapter before registering it.'),

      ...issueBlock('M-04', 'MEDIUM', 'Nested backend/backend/ Directory Is Dead Code',
        'backend/backend/app/',
        'A nested backend/backend/app/ directory exists alongside the real backend/app/. It appears to be a leftover from a directory restructure. It is not imported anywhere but it occupies disk space and can confuse tooling (linters, import resolvers) that scan the entire project tree.',
        'Any static analysis tool that scans backend/ will find duplicate module names and report false positives. New developers may be confused about which backend/app/ is authoritative.',
        'Delete backend/backend/ entirely. Verify no import in the real source resolves to it.'),

      ...issueBlock('M-05', 'MEDIUM', 'workflow.json QA Stage Shows No Dependencies (Missing Sprint Gate)',
        'app/workflow/workflow.json',
        '"qa" stage has "requires": [] — suggesting it depends on nothing. In reality QA must not run until all sprints are complete. This is enforced by the state machine (ALL_SPRINTS_COMPLETE state), not the dependency graph. But DependencyGraph.has_dependency("qa") returns False, and any component that trusts the graph will conclude QA can run in parallel with or before sprints.',
        'DependencyGraph is unreliable as a source of truth. Future tooling built on it (impact analysis, partial-pipeline resumption) may produce incorrect ordering.',
        'Add a conceptual "sprints_complete" emitted artifact to workflow.json and list it as a requirement for qa. Document sprint-internal stages even if marked sprint_scope: true.'),

      ...issueBlock('M-06', 'MEDIUM', 'No CORS Configuration — API Open to Any Origin',
        'app/main.py  +  app/api/router.py',
        'No CORSMiddleware is added to the FastAPI application. By default FastAPI does not add CORS headers. A browser on a different origin cannot call the API. The Vite dev server proxies /api to localhost:8000 so development works, but once the frontend and backend are deployed to different origins (common in production), all API calls will be blocked by the browser\'s CORS policy.',
        'The application cannot be deployed with the frontend on a CDN and the backend on a server without breaking all browser-originated API calls.',
        'Add app.add_middleware(CORSMiddleware, allow_origins=[...], allow_methods=["*"], allow_headers=["*"]) in create_application(). Configure the allowed origins via an ALLOWED_ORIGINS env var.'),

      ...issueBlock('M-07', 'MEDIUM', 'No Authentication on Any API Endpoint',
        'app/api/ — all routers',
        'There is no authentication layer on any API endpoint. Any client with network access can create projects, trigger pipeline runs, read all artifacts, delete workspaces, and reconfigure the LLM provider including API keys.',
        'In any networked deployment (local LAN, cloud), the entire system is open. The /settings endpoint exposes and accepts LLM provider API keys with no auth.',
        'Add API-key or token-based authentication as a FastAPI dependency on all routers. At minimum protect /settings and /workflow/* endpoints.'),

      divider(),

      // ── LOW ISSUES ──
      h1('6. Low-Severity Issues & Code Quality'),

      bold('L-01 — Frontend Total Stage Count Hardcoded (total_stages: 11 in EMPTY state)'),
      p('usePipeline.ts hardcodes total_stages: 11 in the EMPTY state. The backend sends the real count in the status response but the initial render shows 11. If the pipeline ever adds or removes a top-level stage the frontend progress bar will be wrong on first render.'),

      bold('L-02 — run.sh Assumes System Python Has pytest'),
      p('run.sh runs python -m pytest without activating the .venv. If pytest is only installed in the virtual environment (which it should be), the check fails with "No module named pytest" and the server never starts. The venv must be activated before run.sh is called, but this is not documented.'),

      bold('L-03 — config.yaml max_tokens Differs from Settings Default'),
      p('config.yaml sets max_tokens: 4096. Settings.LLMConfig defaults to max_tokens=8192 (with a comment explaining why 4096 causes truncation). If the yaml is read without the default override, stages that need 8192 tokens will truncate. The discrepancy between the file and the model default is a latent bug for anyone who edits config.yaml.'),

      bold('L-04 — ClaudeProvider Lists Unversioned Model Names in _KNOWN_MODELS'),
      p('"claude-opus-4-5", "claude-sonnet-4-5", "claude-opus-4-0", "claude-sonnet-4-0" are listed without date stamps. The Anthropic API requires date-stamped IDs and returns HTTP 404 for undated aliases. These entries are mentioned as known issues in the code comment but remain in the list.'),

      bold('L-05 — LearningLoop.get_relevant_patterns() project_id Scope Fix Still Has a Gap'),
      p('The comment in WorkflowEngine._with_relevant_patterns() describes a bug where patterns from one project leaked into another. The fix adds project_id scoping. However, LearningLoop.record_trajectory() is also called from Reviewer._record_finding_patterns() WITHOUT a project_id, so rejected-review trajectories are stored globally and can still surface across projects.'),

      bold('L-06 — PipelineSupervisor Imports WorkspaceManager Twice'),
      p('pipeline_supervisor.py has from ..workspace.manager import WorkspaceManager on two consecutive lines (duplicate import). Harmless but indicates the file was edited hastily.'),

      bold('L-07 — backend/memory/memory.db and data/ Duplicate Memory Files'),
      p('backend/memory/memory.db is a legacy SQLite file from the flat-file era. backend/data/ contains the current databases. The old file is never written to but sits alongside the repo, adding to the confusion about which database is live.'),

      divider(),

      // ── PIPELINE STATUS ──
      h1('7. Pipeline Functional Assessment'),

      h2('7.1 What Works'),
      bullet('Project creation (POST /project), workspace layout, project.json state machine — solid.'),
      bullet('WorkflowEngine execute → review → retry loop — correct logic, good reviewer with AUTO_FIX/ASK_HUMAN/FLAG tiers.'),
      bullet('Checkpoint save/delete on success and failure paths — crash recovery works.'),
      bullet('LearningLoop trajectory recording and pattern injection — wired correctly in WorkflowEngine (except the project_id scope gap noted in L-05).'),
      bullet('LessonStore extraction on approval — correctly implemented.'),
      bullet('Design context injection for FrontendDeveloper and QA stages — works.'),
      bullet('Design review pause/resume/approve flow — correctly implemented in workflow.py.'),
      bullet('WebSocket EventBroadcaster — correct thread-safe implementation using bound loop; stage_started/stage_complete/log_line events work.'),
      bullet('ExecutionStateRegistry — thread-safe with Lock, prevents duplicate pipeline starts.'),
      bullet('Frontend real-time log panel, WebSocket reconnect with exponential backoff — well implemented.'),
      bullet('Multiple LLM provider support (Ollama, Claude, Gemini, Bedrock) — factory pattern is clean.'),
      bullet('SafetyPolicy workspace boundary check — prevents writes outside the project workspace.'),

      h2('7.2 What Is Broken or Unreliable'),
      bullet('CRITICAL: Dual container — kernel lifecycle manages orphan container; API routes use a separate one. Shutdown logic for API container never runs.'),
      bullet('CRITICAL: LLM progress messages silently dropped in background threads (B-02).'),
      bullet('CRITICAL: Every agent gets a fresh LLMManager with no DI wiring (B-03).'),
      bullet('CRITICAL: Model mismatch causes first pipeline run to fail silently after clean startup (B-04).'),
      bullet('HIGH: Sprint execution is a UI black box — no stage events emitted, progress stuck.'),
      bullet('HIGH: SprintRetryConfig settings have no effect — sprint retries are always limited to 2.'),
      bullet('MEDIUM: MemoryOrchestrator is a broken singleton that will crash if resolved.'),
      bullet('MEDIUM: No CORS → production browser deployment is broken.'),
      bullet('MEDIUM: No auth → all API endpoints are open to any network client.'),

      divider(),

      // ── UPGRADE RECOMMENDATIONS ──
      h1('8. Upgrade Recommendations (Priority Order)'),

      h2('8.1 Immediate — Must Fix Before Any Demo or Test'),
      bullet('Fix B-01: Collapse to a single Container; kernel.container = api container.'),
      bullet('Fix B-04 + B-05: Sync run.sh model check with .env; fix .env.example key names.'),
      bullet('Fix B-02: Replace ws_manager.broadcast_sync() in LLMManager with EventBroadcaster injection.'),
      bullet('Fix B-03: Pass llm_manager from Container into AgentFactory.create().'),

      h2('8.2 Short Term — Before Production'),
      bullet('A-01: Convert pipeline to async or use dedicated per-project thread with bounded executor.'),
      bullet('A-02: Remove API-layer import from LLM layer; inject broadcaster.'),
      bullet('A-03: Emit sprint sub-stage events and add them to frontend STAGES list.'),
      bullet('M-06: Add CORSMiddleware with configurable allowed origins.'),
      bullet('M-07: Add token/API-key authentication to all endpoints.'),
      bullet('A-04: Wire SprintRetryConfig into _run_sprint_with_retry.'),

      h2('8.3 Medium Term — Architecture Quality'),
      bullet('Introduce async LLM calls with asyncio.to_thread() to eliminate threadpool saturation.'),
      bullet('Add a health check that validates: Ollama reachable + configured model pulled + all DB paths writable.'),
      bullet('Move all database paths to absolute resolution in ConfigurationLoader.'),
      bullet('Remove MemoryOrchestrator or complete it; remove the dead backend/backend/ directory.'),
      bullet('Add integration tests that boot the real FastAPI app and run at least one stage end-to-end.'),
      bullet('Wire ConfigurationManager singleton through DI rather than re-instantiating it in every class.'),

      h2('8.4 Future — Platform Maturity'),
      bullet('Async WebSocket streaming of partial LLM tokens (currently the full response is awaited then pushed).'),
      bullet('Project-level concurrency: one async task tree per project, proper cancellation on stop.'),
      bullet('Structured logging with trace/span IDs (project_id + stage + attempt) across all components.'),
      bullet('Persistent CostTracker (currently in-memory; restarting the server loses all cost data).'),
      bullet('Plugin/hook system for custom agents without modifying AgentFactory.'),
      bullet('Multi-user support: user identity on projects, row-level security on WorkspaceManager.'),

      divider(),

      // ── CLOSING ──
      h1('9. Conclusion'),
      p('AI DevOS demonstrates a sophisticated understanding of multi-agent orchestration. The pipeline design, three-tier reviewer, LearningLoop integration, and WebSocket event model are all architecturally sound and well-commented. The codebase is clearly the product of iterative development with genuine quality thinking.'),
      p('The critical bugs are not design failures — they are integration gaps introduced during rapid iteration (dual container, model mismatch, thread-safety in broadcasts). They are all fixable in one focused sprint. Once B-01 through B-05 are resolved, the platform will have a reliable foundation to build on.'),
      p('The highest-leverage single change is fixing B-01 (dual container) because it is the root cause of unpredictable state across every subsystem. All other fixes become more tractable once there is a single authoritative container.'),

      new Paragraph({
        children: [new TextRun({ text: 'Report generated by static analysis of 150+ source files. No code was modified.', size: 18, color: '888888', italics: true })],
        alignment: AlignmentType.CENTER, spacing: { before: 400 },
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/sessions/optimistic-elegant-fermat/mnt/AI-DevOS3/AI_DevOS_Full_Analysis_Report.docx', buf);
  console.log('Done');
});
