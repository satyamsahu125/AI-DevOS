# 12-Stage Pipeline Specification

**Last Updated**: 2026-07-25  
**Status**: Canonical stage sequence  
**Authority**: Defined in `backend/app/workflow/dependency_graph.py::STAGE_ORDER`  

---

## Overview

The pipeline is a **fixed 12-stage sequence** where each stage:
1. Reads the previous stage's approved output (+ context from earlier stages)
2. Executes an LLM-backed agent
3. Validates the output against a schema
4. Passes through a three-tier reviewer
5. Either approves and moves to the next stage, OR retries with feedback (max 3 attempts)

**Key Design**: Only stages 7-8 (Backend/Frontend Developer) write to disk. All other stages produce reviewable documents.

---

## Stage Table

| # | Stage | Agent | Produces | Depends On | Reviewer Gate |
|---|-------|-------|----------|-----------|---------------|
| **1** | **Strategic Review** | StrategicReviewAgent | Go/no-go assessment of viability | None (first stage) | Viability is justified; scope mode explicit |
| **2** | **Product Owner** | ProductOwnerAgent | Requirements, user stories, acceptance criteria | Strategic Review | Requirements complete, no ambiguity, criteria testable |
| **3** | **Architect** | ArchitectAgent | Architecture: modules, APIs, data models, tech stack | Product Owner | Architecture satisfies all requirements; dependencies acyclic |
| **4** | **Designer** | DesignerAgent | Design spec: pages, components, layouts, design system | Architect | Design completes the architecture; design system consistent |
| **5** | **Security** | SecurityAgent | Security review: threats, findings, mitigations | Designer | Every CRITICAL finding has exploit scenario + remediation |
| **6** | **File Planner** | FileStructurePlannerAgent | Concrete file list (path, module, purpose, responsible_stage) | Security + Architect + Designer | Every architecture module mapped to files; no overlaps |
| **7** | **Backend Developer** | BackendDeveloperAgent | **REAL backend source files** (one LLM call per file) | File Plan + Security + Architect | Code matches architecture; all planned backend files present |
| **8** | **Frontend Developer** | FrontendDeveloperAgent | **REAL frontend source files** (one LLM call per file) | File Plan + Designer + Architect | Code matches design; consumes actual backend API |
| **9** | **QA** | QAAgent | QA test plan, bug list, health score | Backend + Frontend | Health score computed; every fix has regression test |
| **10** | **Document** | DocumentAgent | Project documentation (guides, API docs, deployment) | QA | Every user-facing change has corresponding doc update |
| **11** | **DevOps** | DevOpsAgent | Deployment guidance (Docker, Kubernetes, ops runbooks) | Document + Security | No CRITICAL security finding deployed unmitigated |
| **12** | **Retro** | RetroAgent | Retrospective: lessons learned, success factors | DevOps | At least one concrete, actionable lesson identified |

**Workflow terminates** after Retrospective is approved.

---

## Execute → Review → Retry Cycle

Every stage runs through this cycle:

```
Stage.Execute()
  ├─ Build prompt (via PromptBuilder)
  ├─ Call LLM (via LLMManager)
  ├─ Parse + validate output (via action.run())
  ├─ Save artifact attempt (ArtifactManager.save_artifact())
  │
  └─→ Reviewer.review(artifact)
      ├─ Check schema compliance
      ├─ Check content quality (min chars, structure)
      ├─ Check domain-specific rules (Designer: design system; Backend/Frontend: file coverage)
      │
      ├─→ IF approved (no ASK_HUMAN findings):
      │   ├─ Record Trajectory (for learning loop)
      │   ├─ Embed in KnowledgeMemory (if approved)
      │   ├─ Write Lesson (human-readable)
      │   ├─ Store predecessor message (for next stage)
      │   └─ → NEXT STAGE
      │
      └─→ ELSE (rejected with ASK_HUMAN findings):
          ├─ Inject feedback into retry prompt
          ├─ Retry (up to RetryPolicy.max_retries = 3)
          └─ If max retries exhausted → Stage FAILED
```

---

## Review Tiers

| Tier | Definition | Blocks Approval? | Example |
|------|-----------|-----------------|---------|
| **AUTO_FIX** | Mechanical issue; never a blocker | NO | "Empty requirements section; auto-populated" |
| **ASK_HUMAN** | Reasonable engineers could disagree | **YES** | "Architecture doesn't cover security requirements" |
| **FLAG** | Advisory; notable but not blocking | NO | "Token count high for this stage; may retry" |

Approval happens **only when there are zero ASK_HUMAN findings**.

---

## Memory Flow

Each stage reads context from previous stages via **project-scoped memory**:

### Stage 1 (Strategic Review)
- **Reads**: None (first stage)
- **Writes**: Strategic assessment

### Stages 2-6 (Requirements → File Plan)
- **Reads**: Approved artifact from previous stage
- **Writes**: Next stage's input

### Stages 7-8 (Backend/Frontend Developer)
- **Reads**: File Plan + approved Architect artifact + approved Designer artifact (for Frontend)
- **Writes**: Real files to `temp-workspace/{project_id}/project/{backend|frontend}/`

### Stages 9-12 (QA → Retro)
- **Reads**: All previous approved artifacts (full context)
- **Writes**: Next stage's input (or terminates)

**Project Isolation**: All memory reads/writes prefixed with `{project_id}:`, so two projects never see each other's state.

---

## Dependency Graph

```
1. StrategicReview
   ↓
2. ProductOwner
   ↓
3. Architect ←─────────┐
   ↓                   │
4. Designer ←─────────┐│
   ↓                  ││
5. Security          ││
   ↓                  ││
6. FilePlanner ←─────┘│ (reads Architect + Designer for context)
   ↓
   ├─→ 7. Backend (reads FilePlan + Architect context)
   └─→ 8. Frontend (reads FilePlan + Designer context)
   ↓
9. QA (reads all previous)
   ↓
10. Document (reads all previous)
   ↓
11. DevOps (reads all previous)
   ↓
12. Retro (reads all previous)
   ↓
✓ Pipeline Complete
```

---

## Critical Design Decisions

### 1. One LLM Call Per File (Stages 7-8)
**Why**: Asking "write entire backend in one call" fails on small models. One-file-per-call is more reliable.

**How**: 
- File Planner gives Backend/Frontend a concrete list
- Backend/Frontend loop: for each file → generate → validate → write
- Max 3 retries per file

**Result**: Reliable code generation on qwen2.5-coder:7b (7B param local model)

### 2. No Code Before File Plan
**Why**: Without a file structure, agents diverge and produce unmergeable code.

**How**: 
- Stages 1-6 plan; Stages 7-8 execute
- File Plan is the single source of truth

**Result**: Clear separation between "what should we build" and "let's build it"

### 3. Designer Context Flows to Frontend Only
**Why**: Frontend needs exact design specs. Backend doesn't.

**How**:
- File Planner reads Designer output
- Frontend Agent reads Designer output
- Backend Agent reads Architect output

**Result**: Frontend code matches design; backend code matches architecture

### 4. Security Review Early (Stage 5)
**Why**: Design-time security review catches issues before code exists.

**How**: 
- Security agent reviews the Architecture + Design
- Identifies CRITICAL findings
- Dev agents read security findings as context

**Result**: Security is a constraint, not an afterthought

### 5. Three-Tier Review (AUTO_FIX/ASK_HUMAN/FLAG)
**Why**: Mirrors real human review where some things are mechanical, some need judgment.

**How**:
- AUTO_FIX: "Content empty" → don't block
- ASK_HUMAN: "Missing security review" → block and retry with feedback
- FLAG: "Token count high" → note but approve

**Result**: Real quality gates, not just "is content non-empty"

---

## Stage Responsibilities (Detailed)

### Stage 1: Strategic Review
**Input**: Raw user request (e.g., "Build a todo app")  
**Output**: Strategic assessment (go/no-go, scope mode, risks)  
**Reviewer Checks**: Viability is justified; scope mode chosen (Expansion/Selective/Hold/Reduction)  
**Next Stage Reads**: Strategic assessment as context

---

### Stage 2: Product Owner
**Input**: Strategic assessment + business context  
**Output**: Requirements (goals, user stories, acceptance criteria)  
**Reviewer Checks**: Requirements are complete, unambiguous, criteria are testable  
**Next Stage Reads**: Requirements artifact

---

### Stage 3: Architect
**Input**: Requirements  
**Output**: Architecture (modules, APIs, data models, tech stack)  
**Reviewer Checks**: Architecture satisfies every requirement; no circular dependencies  
**Key**: Later stages (Designer, FilePlanner) read this as the blueprint  

---

### Stage 4: Designer
**Input**: Architecture  
**Output**: Design spec (pages, components, design system colors/fonts/spacing)  
**Reviewer Checks**: Design covers all architecturally-defined endpoints; design system consistent  
**Key**: Frontend Developer reads this for exact design

---

### Stage 5: Security
**Input**: Architecture + Design  
**Output**: Security report (CRITICAL/HIGH/MEDIUM findings, exploit scenarios, mitigations)  
**Reviewer Checks**: Every CRITICAL finding has exploit scenario + concrete remediation  
**Key**: Dev agents read security findings as implementation constraints

---

### Stage 6: File Planner
**Input**: Architecture + Design + Security + Requirements  
**Output**: Concrete file list (path, module, purpose, responsible_stage)  
**Reviewer Checks**: Every architecture module → at least one file; no overlaps; paths are valid  
**Key**: Backend/Frontend agents use this as their work assignment

---

### Stage 7: Backend Developer
**Input**: File Plan (backend files only) + Architecture + Security context  
**Output**: Real Python/Node files written to `temp-workspace/{id}/project/backend/`  
**Process**:
1. For each backend file in File Plan:
   - Generate source code (one LLM call)
   - Validate syntax
   - Write to disk
   - Retry up to 3x if validation fails
2. Scan all written files for imports
3. Auto-generate `requirements.txt` from detected imports

**Reviewer Checks**: All planned backend files present; no coverage gaps  
**Key**: Only agent that writes to disk

---

### Stage 8: Frontend Developer
**Input**: File Plan (frontend files only) + Design + Architecture context  
**Output**: Real JavaScript/TypeScript files written to `temp-workspace/{id}/project/frontend/`  
**Process**: Same as Backend (one file per LLM call) + auto-generate `package.json`  
**Reviewer Checks**: All planned frontend files present; code consumes actual Backend API  
**Key**: Only agent that writes to disk

---

### Stage 9: QA
**Input**: Generated backend code + frontend code + requirements + security review  
**Output**: QA test plan (health score per category, bugs, ship readiness)  
**Reviewer Checks**: Health score computed; every fix has regression test noted  
**Next Stages Read**: QA report as context for documentation/deployment

---

### Stage 10: Document
**Input**: All previous approved artifacts  
**Output**: Project documentation (README, API docs, deployment guide)  
**Reviewer Checks**: Every user-facing code change has corresponding doc update  
**Next Stages Read**: Documentation updated

---

### Stage 11: DevOps
**Input**: Generated code + security review + QA report  
**Output**: Deployment guidance (Docker/Kubernetes manifests, ops runbooks)  
**Reviewer Checks**: No CRITICAL security finding deployed unmitigated  
**Purpose**: Make the project runnable

---

### Stage 12: Retro
**Input**: All previous artifacts + execution metrics  
**Output**: Retrospective (lessons learned, success factors)  
**Reviewer Checks**: At least one concrete, actionable lesson identified  
**Purpose**: Capture insights for future projects  
**Terminates Pipeline**: ✓ Complete

---

## When a Stage Fails

If a stage exhausts its retries (3 attempts) without approval:

1. **Stage Status**: FAILED
2. **Pipeline Status**: PAUSED (can be manually retried)
3. **Previous Stages**: Remain approved
4. **Recovery**: User can retry the failed stage via `POST /workflow/{id}/retry`

---

## Project Isolation

Every stage respects project isolation:

- **Memory**: Reads/writes are `{project_id}:{key}`
- **Workspace**: Files in `temp-workspace/{project_id}/project/`
- **Artifacts**: Saved in `{project_id}` namespace
- **Execution**: Two projects never see each other's data

Two projects can run concurrently; the pipeline maintains complete isolation.

---

## For More Details

- **Stage Implementation**: `backend/app/agents/` (12 agent classes)
- **Review Rules**: `backend/app/review/rules.py` (23+ checks)
- **Dependency Graph**: `backend/app/workflow/dependency_graph.py`
- **Retry Policy**: `backend/app/workflow/retry_policy.py`
- **Memory Flow**: `backend/app/memory/manager.py` + `memory_manager.py`

