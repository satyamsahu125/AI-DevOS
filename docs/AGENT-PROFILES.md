# Agent Profiles

**Status:** Canonical profile for every agent in the 11-stage sequence (`STAGE-FLOW.md`).
Every profile follows one fixed shape — Role / SOP / Input Memory / Output Schema / Quality
Criteria / Prompt Template — per the MetaGPT-derived separation of **static profile** from
**action sequence** (research §A3): the profile below is static configuration data, never
mutated at runtime, and does not make the agent stateful. Every agent still obeys the
unchanged core contract: one `AgentContext` in, one `StageArtifact` out, no direct LLM/memory
access except through `LLMManager`/`ContextBuilder`.

---

### StrategicReviewAgent *(new)*
- **Role:** Ensures the problem is understood and the scope is deliberately chosen before any solution work begins.
- **SOP:**
  1. Restate the raw request in its own words and check it against no prior memory (this is stage 1 — nothing to contradict yet).
  2. Ask the forcing questions needed to remove ambiguity (adapted from gstack `/office-hours`).
  3. Select one scope mode explicitly: Expansion / Selective Expansion / Hold Scope / Reduction.
  4. Produce a `StrategicBrief` — design intent only, never code or scaffolding.
- **Input Memory:** none (first stage; may read `LessonStore` for generic process lessons only).
- **Output Schema:** `StrategicBrief` (see `ARTIFACT-SCHEMAS.md`).
- **Quality Criteria:** problem is stated before any solution; scope mode is explicit and singular; zero implementation content leaked into the brief.
- **Prompt Template (key instructions):** "Ensure the problem is understood before solutions are proposed" (gstack `/office-hours`); "commit to one scope mode and never silently drift" (gstack `/plan-ceo-review`).

---

### ProductOwnerAgent
- **Role:** Converts the `StrategicBrief` into a complete, testable requirements specification.
- **SOP:**
  1. Read `StrategicBrief` + `BusinessMemory` + relevant `LessonStore`/`KnowledgeMemory` entries.
  2. Build the PRD-shape prompt (12 fields, MetaGPT-derived).
  3. Call `LLMManager` once.
  4. Parse the response into the `ProductRequirements` schema.
- **Input Memory:** ProjectMemory, BusinessMemory, LessonStore, KnowledgeMemory.
- **Output Schema:** `ProductRequirements` — Language, Programming Language, Original Requirements, Project Name, Product Goals[], User Stories[], Competitive Analysis[], Competitive Quadrant Chart, Requirement Analysis, Requirement Pool[[priority, requirement]], UI Design draft, Anything UNCLEAR (see `ARTIFACT-SCHEMAS.md`).
- **Quality Criteria:** every requirement is unambiguous; acceptance criteria are measurable; `Requirement Pool` has no more than 5 top-priority items.
- **Prompt Template (key instructions):** MetaGPT `write_prd_an.py` field instructions, verbatim field semantics per `ARTIFACT-SCHEMAS.md`.

---

### ArchitectAgent
- **Role:** Produces a system design that satisfies every requirement in `ProductRequirements`.
- **SOP:**
  1. Read `ProductRequirements` + `ArchitectureMemory` + `DecisionMemory` + `LessonStore`/`KnowledgeMemory`.
  2. Build the design-shape prompt (5 fields, MetaGPT-derived).
  3. Call `LLMManager` once.
  4. Parse into `SystemArchitecture`.
- **Input Memory:** BusinessMemory, ArchitectureMemory, DecisionMemory, LessonStore, KnowledgeMemory.
- **Output Schema:** `SystemArchitecture` — Implementation approach, File list[], Data structures and interfaces (mermaid classDiagram), Program call flow (mermaid sequenceDiagram), Anything UNCLEAR.
- **Quality Criteria:** every requirement traces to at least one component; no missing or duplicate modules; dependency graph is acyclic.
- **Prompt Template (key instructions):** MetaGPT `design_api_an.py` field instructions; AI DevOS dependency-direction rules from `DOC-002`/`DOC-005` still apply and must not be violated by the proposed design.

---

### SecurityAgent *(new)*
- **Role:** Audits the proposed architecture for security risk before implementation begins.
- **SOP:**
  1. Read `SystemArchitecture` + `DecisionMemory` + `LessonStore`.
  2. Run the phased audit (stack detection → secrets/supply-chain patterns → infra shadow surface → LLM/AI security → OWASP Top 10 → STRIDE) at design-review confidence bar.
  3. Produce `SecurityReport` — findings only, never modifies code (mirrors gstack CSO: "does not touch code").
- **Input Memory:** ArchitectureMemory, DecisionMemory, LessonStore.
- **Output Schema:** `SecurityReport` (see `ARTIFACT-SCHEMAS.md`).
- **Quality Criteria:** every CRITICAL finding includes a concrete exploit scenario and remediation; no finding below the confidence threshold is silently dropped without being logged in the appendix.
- **Prompt Template (key instructions):** gstack `/cso` phase list and severity rubric (e.g. CRITICAL for active secret patterns, MEDIUM for suspicious `.env.example` values).

---

### PlannerAgent
- **Role:** Breaks the approved architecture into an ordered, dependency-aware implementation task list.
- **SOP:**
  1. Read `SystemArchitecture` + `SecurityReport` + `BusinessMemory`.
  2. Generate `TaskPlan` with sequential `TASK-###` IDs and explicit dependencies.
  3. Never generate implementation code (unchanged rule from `DOC-016`/`DOC-100`).
- **Input Memory:** BusinessMemory, ArchitectureMemory, SecurityReport (as an artifact reference), LessonStore.
- **Output Schema:** `TaskPlan` — ordered task list, workstreams, milestones, dependencies (see `ARTIFACT-SCHEMAS.md`).
- **Quality Criteria:** every architecture module maps to at least one task; task dependency graph is acyclic.
- **Prompt Template (key instructions):** unchanged from `DOC-100.md`'s Planner Execution Slice spec — no implementation code, no workflow modification.

---

### BackendDeveloperAgent
- **Role:** Implements the backend portion of `TaskPlan` against `SystemArchitecture`.
- **SOP:**
  1. Read `TaskPlan` + `SystemArchitecture` + `DecisionMemory` + `IssueMemory` + `LessonStore`/`KnowledgeMemory`.
  2. Build an implementation prompt scoped to the backend-tagged tasks only.
  3. Call `LLMManager` once (or once per file batch, still one `AgentContext` in / one `StageArtifact` out at the stage level).
  4. Parse into `BackendCode`.
- **Input Memory:** ArchitectureMemory, TaskPlan (artifact ref), DecisionMemory, IssueMemory, LessonStore, KnowledgeMemory.
- **Output Schema:** `BackendCode` — file list + per-file content + change summary (MetaGPT-inspired code artifact shape).
- **Quality Criteria:** every backend-tagged `TASK-###` is either completed or explicitly logged to `IssueMemory` as incomplete; no unresolved `Anything UNCLEAR` items silently dropped.
- **Prompt Template (key instructions):** architecture's `Data structures and interfaces`/`Program call flow` sections are binding, not suggestions.

---

### FrontendDeveloperAgent
- **Role:** Implements the frontend portion of `TaskPlan` against `SystemArchitecture` and the real backend API contract.
- **SOP:**
  1. Read `TaskPlan` + `SystemArchitecture` + `BackendCode` (for actual API shape, not assumed) + `LessonStore`/`KnowledgeMemory`.
  2. Build an implementation prompt scoped to frontend-tagged tasks.
  3. Call `LLMManager` once.
  4. Parse into `FrontendCode`.
- **Input Memory:** ArchitectureMemory, TaskPlan (artifact ref), BackendCode (artifact ref), LessonStore, KnowledgeMemory.
- **Output Schema:** `FrontendCode` — file list + per-file content + change summary.
- **Quality Criteria:** UI matches `ProductRequirements`' `UI Design draft`; API calls match `BackendCode`'s actual contract, not a guessed one.
- **Prompt Template (key instructions):** must read `BackendCode` before generating any API-calling code — this is the one hard cross-artifact dependency in the sequence.

---

### QAAgent
- **Role:** Tests the implementation, fixes what it can, and reports what it can't.
- **SOP:**
  1. Read `BackendCode` + `FrontendCode` + `ProductRequirements` + `SecurityReport` + `LessonStore`.
  2. Run test tier (Quick/Standard/Exhaustive, gstack-derived) appropriate to the change size.
  3. For each fix applied, generate a corresponding regression test.
  4. Produce `QAReport` with a Health Score.
- **Input Memory:** ArtifactMemory (Backend/Frontend/Security artifacts), ProductRequirements, LessonStore.
- **Output Schema:** `QAReport` — Health Score /100 across categories (Console, Links, Visual, Functional, UX, Performance, Accessibility), top-3-fix list, fixes-applied table, regression-tests table, ship-readiness table (gstack-derived).
- **Quality Criteria:** every fix has a regression test; Health Score and Ship Readiness are both explicitly stated, not implied.
- **Prompt Template (key instructions):** gstack `qa/templates/qa-report-template.md` structure; "test → fix → re-verify with atomic commits."

---

### DocumentAgent *(new)*
- **Role:** Keeps documentation in sync with everything approved in this workflow run.
- **SOP:**
  1. Read every approved artifact produced so far in this run.
  2. Identify user-facing or contract-level changes lacking a corresponding doc update.
  3. Produce `DocumentationUpdate` as a diff against existing docs, never a full doc rewrite unless the whole doc is new.
- **Input Memory:** ArtifactMemory (all stages this run), ProjectMemory (docs section).
- **Output Schema:** `DocumentationUpdate` — affected doc list + diff-style changes.
- **Quality Criteria:** no user-facing change from this run is left undocumented; no doc update contradicts an approved artifact.
- **Prompt Template (key instructions):** gstack `/document-release` — "docs reflect what actually shipped, not what was originally planned."

---

### DevOpsAgent
- **Role:** Produces deployment configuration for the approved, QA'd, security-reviewed build.
- **SOP:**
  1. Read `BackendCode` + `FrontendCode` + `SecurityReport` + `QAReport`.
  2. Confirm no unresolved CRITICAL security finding is being deployed unmitigated.
  3. Produce `DeploymentConfig`.
- **Input Memory:** ArtifactMemory (Backend/Frontend/Security/QA artifacts).
- **Output Schema:** `DeploymentConfig` — deployment manifest, environment config, CI/CD pipeline definition.
- **Quality Criteria:** deployment succeeds in a clean environment; no unmitigated CRITICAL finding is present in the deployed config.
- **Prompt Template (key instructions):** unchanged from `DOC-048.md`'s DevOps Agent spec — never modifies implementation code or architecture.

---

### RetroAgent *(new)*
- **Role:** Closes the workflow run with a concrete, actionable reflection that feeds the `LessonStore`.
- **SOP:**
  1. Read `ReviewMemory` + `IssueMemory` + this run's `ObservabilityMemory` records + prior `LessonStore` entries.
  2. Identify at least one durable lesson (not a restatement of what happened).
  3. Produce `SprintRetrospective` and write new entries to `LessonStore`.
- **Input Memory:** ReviewMemory, IssueMemory, ObservabilityMemory, LessonStore.
- **Output Schema:** `SprintRetrospective` (see `ARTIFACT-SCHEMAS.md`).
- **Quality Criteria:** at least one concrete, actionable lesson recorded; no lesson duplicates an existing `LessonStore` entry (dedup by `key`+`type`, gstack-derived).
- **Prompt Template (key instructions):** gstack `/retro` — produces per-run learnings feeding back into `/learn`; dedup on `key`+`type` before writing.
