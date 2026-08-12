# Operational System Flow Document — AI DevOS

> **Source of Truth**: Reverse-engineered from `backend/app/main.py`, `backend/app/workflow/engine.py`, `backend/app/workflow/stage_runner.py`, `backend/app/workflow/sprint_executor.py`, and `frontend/src/`.

---

## 1. End-to-End Operational Lifecycle

The system operates across six distinct runtime phases:

```text
1. Application Startup & Initialization
   ↓
2. Project Creation & Workspace Initialization
   ↓
3. Pipeline Stage Execution (Clarification -> Product Owner -> Architect -> Security -> Sprint Planner)
   ↓
4. Sprint Execution Loop (Scrum Master -> File Delta -> File Planner -> Backend/Frontend Dev -> Deploy -> Review)
   ↓
5. Quality Assurance & Bug Replanning (QA Orchestrator -> Bug Analyst -> Retry Engine)
   ↓
6. Artifact Stamping, Documentation, Retro & Project Completion
```

---

## 2. Sequence Diagrams

### 2.1 Application Startup Flow

```mermaid
sequenceDiagram
    autonumber
    participant Uvicorn as Uvicorn Process
    participant Main as app.main
    participant Kernel as AIKernel
    participant DB as SQLite Storage Adapters
    participant LLM as LLM Manager
    participant Mem as HNSW & Vector Memory
    participant Engine as Workflow Engine

    Uvicorn->>Main: Execute lifespan context manager
    Main->>Kernel: start()
    Kernel->>DB: initialize_all_databases() (auth, memory, costs, file_index, learning)
    Kernel->>LLM: initialize_providers() (OpenAI, Anthropic, Gemini, Ollama)
    Kernel->>Mem: load_hnsw_indexes()
    Kernel->>Engine: start()
    Main->>Main: bind_loop(asyncio.get_running_loop()) [Broadcaster WS Event Loop]
    Uvicorn-->>Main: FastAPI Application Ready on 0.0.0.0:8000
```

---

### 2.2 Project Creation & Workflow Dispatch Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Frontend UI
    participant API as /api/v1/projects (FastAPI)
    participant Auth as Auth & APIKey Middleware
    participant ProjMgr as Project Manager
    participant Engine as Workflow Engine
    participant Celery as Celery Queue / Task
    participant DB as SQLite Storage

    User->>Auth: POST /api/v1/projects (Bearer JWT / API Key)
    Auth->>API: Validated Request
    API->>ProjMgr: create_project(name, description, config)
    ProjMgr->>DB: Save project row (status: CREATED)
    ProjMgr->>DB: Create requirement version 1
    API->>Engine: start_workflow(project_id)
    alt Celery / Redis Available
        Engine->>Celery: send_task("app.tasks.pipeline_task.run_pipeline", project_id)
        Celery-->>Engine: task_id returned
    else Celery / Redis Unavailable (Fallback)
        Engine->>Engine: BackgroundTasks.add_task(run_pipeline, project_id)
    end
    Engine->>DB: Update project status: RUNNING
    API-->>User: 201 Created { project_id, status: "RUNNING" }
```

---

### 2.3 Sprint Code Generation & Deploy Validation Flow

```mermaid
sequenceDiagram
    autonumber
    participant SprintExec as Sprint Executor
    participant Delta as SprintDelta Stage
    participant FilePlanner as FileStructurePlanner Stage
    participant Dev as Backend/Frontend Developer Agents
    participant Syntax as File Syntax Validator
    participant Workspace as Workspace Layout / Disk
    participant Deploy as SprintDeploy Stage
    participant Docker as Docker Sandbox Container

    SprintExec->>Delta: Execute SprintDelta (Sprint 2+ delta classification)
    SprintExec->>FilePlanner: Generate FileStructurePlan (file paths & tech stack)
    FilePlanner-->>SprintExec: FileStructurePlan DTO

    loop For Each File in FileStructurePlan
        SprintExec->>Dev: Invoke Agent (Prompt + Context + Targeted File Schema)
        Dev-->>SprintExec: Generated Code Content
        SprintExec->>Syntax: Validate Syntax (ast.parse for .py / JSON / YAML parser)
        alt Syntax Valid
            SprintExec->>Workspace: Write file to temp-workspace/<project_id>/<file_path>
        else Syntax Invalid
            SprintExec->>Dev: Retry code generation with syntax error context
        end
    end

    SprintExec->>Deploy: Execute SprintDeploy stage
    Deploy->>Docker: Spawn sandbox container & run dependency/build checks
    Docker-->>Deploy: Container stdout, stderr, exit code
    Deploy-->>SprintExec: DeployResult DTO (success/failure)
```

---

### 2.4 Reviewer Gate Rejection & Replanning Flow

```mermaid
sequenceDiagram
    autonumber
    actor Reviewer as Reviewer / User UI
    participant GatesAPI as /api/v1/gates/{project_id}/review
    participant RevMgr as Review Manager
    participant ChangeMgr as Change Manager / Router
    participant Engine as Workflow Engine
    participant DB as SQLite Storage

    Reviewer->>GatesAPI: POST { decision: "Rejected", feedback: "Security flaw in auth endpoint" }
    GatesAPI->>RevMgr: submit_review(project_id, decision, feedback)
    RevMgr->>DB: Record review result (status: REJECTED)
    RevMgr->>ChangeMgr: handle_rejection(project_id, feedback)
    ChangeMgr->>ChangeMgr: Analyze impact (determine affected stage: Architect / Security / Code)
    ChangeMgr->>DB: Create requirement version 2 (increment version)
    ChangeMgr->>Engine: trigger_replanning(project_id, target_stage: "security")
    Engine->>DB: Update workflow state: RUNNING (Rewound to "security")
    GatesAPI-->>Reviewer: 200 OK { project_id, rewound_stage: "security", requirement_version: 2 }
```

---

### 2.5 Real-Time WebSocket Event Broadcasting Flow

```mermaid
sequenceDiagram
    autonumber
    participant Stage as Stage Runner / Agent
    participant Broadcaster as Event Broadcaster (main.py loop)
    participant WSHandler as /api/v1/ws/{project_id}
    actor Client as React Frontend UI

    Client->>WSHandler: Connect WebSocket (ws://host/api/v1/ws/<project_id>)
    WSHandler-->>Client: Connection Accepted

    Stage->>Broadcaster: publish_event(project_id, type="STAGE_PROGRESS", data={...})
    Broadcaster->>Broadcaster: Schedule broadcast on main uvicorn asyncio loop
    Broadcaster->>WSHandler: Forward event frame
    WSHandler-->>Client: JSON Frame { type: "STAGE_PROGRESS", stage: "BackendDeveloper", percent: 45 }
```

---

## 3. Failure Recovery, Cancellation & Resume Mechanics

### 3.1 Failure & Retry Loop
- **Stage Retry**: `app/workflow/retry_engine.py` applies stage-specific retry policies (`max_retries`, backoff delay).
- **Intelligent Replanning**: If retries fail at execution stages, `BugAnalyst` parses log backtraces and adjusts stage inputs before attempting an additional execution pass.

### 3.2 Cancellation Flow
- Endpoint: `POST /api/v1/projects/{project_id}/cancel`.
- Action: Updates project state in `auth.db`/`memory.sqlite` to `CANCELLED`, revokes active Celery task via `celery_app.control.revoke(task_id, terminate=True)`, and notifies connected WebSocket subscribers.

### 3.3 Resume Flow
- Endpoint: `POST /api/v1/projects/{project_id}/resume`.
- Action: Reads latest valid stage checkpoint from `session_state` (`session/checkpoint.py`), reconstructs `StageContext`, and resumes workflow execution from the last uncompleted or failed stage.
