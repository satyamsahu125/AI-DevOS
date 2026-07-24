# Stage Flow (Expanded)

**Status:** Canonical stage sequence, superseding the plain 7-stage sequence in
`DOC-016`/`DOC-072`/`DOC-074`.

## ⚠️ Conflict flagged and resolved: Planner

PROMPT 4's requested 10-stage list (StrategicReview → ProductOwner → Architect →
SecurityReview → BackendDeveloper → FrontendDeveloper → QA → DocumentUpdate → DevOps →
Retrospective) **omits `Planner`**. Planner is not a hypothetical addition — per the codebase
audit (PROMPT 2) it is the **only stage beyond Architect that has any real implementation
today**, and it is part of the fixed roster documented in `DOC-016.MD`, `DOC-072.MD`, and
`DOC-074.MD` (Architect → Planner → BackendDeveloper/FrontendDeveloper). Silently dropping an
already-documented, already-partially-built stage would be a *removal*, not an *addition* —
which the task rule for this prompt explicitly forbids ("Do NOT change the core principles...
Only ADD"). **Resolution: Planner is kept**, inserted between SecurityReview and
BackendDeveloper (security review of the architecture should happen before the architecture is
broken into implementation tasks, so Planner can incorporate security requirements into task
breakdown). This document therefore defines **11 stages**, not 10.

## ⚠️ Conflict flagged: SecurityReview placement

PROMPT 3's research (`SECTION D1`) proposed SecurityReview after QA, modeled on gstack's CSO
skill running as a pre-deployment audit. PROMPT 4 instead places it right after Architect.
Both are defensible; this document adopts PROMPT 4's placement (shift-left security review at
design time, before code exists) since it was explicitly requested and does not conflict with
any core principle — it is purely a sequencing choice within the architect's discretion.

---

## Stage Table

| STAGE | AGENT | INPUT (from which memory) | OUTPUT (artifact type) | OUTPUT SCHEMA | GOES TO (which memory) | REVIEWER CRITERIA |
|---|---|---|---|---|---|---|
| 1. **StrategicReview** | StrategicReviewAgent | Raw user request only (no prior memory — first stage) | `StrategicBrief` | See `ARTIFACT-SCHEMAS.md` | ProjectMemory (metadata section), DecisionMemory (scope mode) | Problem is understood before any solution is proposed; scope mode explicitly chosen (Expansion/Selective/Hold/Reduction); no code or implementation present |
| 2. **ProductOwner** | ProductOwnerAgent | ProjectMemory (metadata), BusinessMemory, LessonStore, KnowledgeMemory | `ProductRequirements` | PRD-shape schema (12 fields, MetaGPT-derived) | BusinessMemory, ProjectMemory, ArtifactMemory | Requirement completeness, no ambiguity, acceptance criteria present and testable |
| 3. **Architect** | ArchitectAgent | BusinessMemory, ArchitectureMemory, DecisionMemory, LessonStore, KnowledgeMemory | `SystemArchitecture` | Design-shape schema (5 fields, MetaGPT-derived) | ArchitectureMemory, DecisionMemory, ArtifactMemory | Architecture satisfies every requirement in `ProductRequirements`; no missing/duplicate modules; dependency direction is acyclic |
| 4. **SecurityReview** | SecurityAgent | ArchitectureMemory, DecisionMemory, LessonStore | `SecurityReport` | CSO-derived phased findings schema | IssueMemory, DecisionMemory (security-locked choices), ArtifactMemory | Every CRITICAL finding has a concrete exploit scenario and a remediation plan; no finding below the confidence threshold suppressed silently |
| 5. **Planner** | PlannerAgent | BusinessMemory, ArchitectureMemory, `SecurityReport`, LessonStore | `TaskPlan` | Task/workstream/dependency list with sequential `TASK-###` IDs | WorkflowMemory, ArtifactMemory | Every architecture module maps to at least one task; dependencies are acyclic; no implementation code present |
| 6. **BackendDeveloper** | BackendDeveloperAgent | ArchitectureMemory, `TaskPlan`, DecisionMemory, IssueMemory, LessonStore, KnowledgeMemory | `BackendCode` | File list + per-file content + summary | ArtifactMemory, IssueMemory (if partial), ObservabilityMemory (call metrics) | Code matches architecture and task scope; no unresolved `TASK-###` left silently incomplete |
| 7. **FrontendDeveloper** | FrontendDeveloperAgent | ArchitectureMemory, `TaskPlan`, `BackendCode` (API contracts), LessonStore, KnowledgeMemory | `FrontendCode` | File list + per-file content + summary | ArtifactMemory, IssueMemory (if partial) | Code matches architecture and consumes the actual backend API contract, not an assumed one |
| 8. **QA** | QAAgent | `BackendCode`, `FrontendCode`, `ProductRequirements`, `SecurityReport`, LessonStore | `QAReport` | Health-score-per-category schema (gstack-derived) | IssueMemory, ReviewMemory, ArtifactMemory | Health Score computed across all categories; every fix has a corresponding regression test; Ship Readiness explicitly stated |
| 9. **DocumentUpdate** | DocumentAgent | Every prior stage's approved artifact for this run | `DocumentationUpdate` | Diff-style doc changes + affected doc list | ArtifactMemory, ProjectMemory (docs section) | Every user-facing change in this run has a corresponding doc update; no doc contradicts an approved artifact |
| 10. **DevOps** | DevOpsAgent | `BackendCode`, `FrontendCode`, `SecurityReport`, `QAReport` | `DeploymentConfig` | Deployment manifest schema | ArtifactMemory, IssueMemory (deployment risks), ObservabilityMemory | Deployment succeeds in a clean environment; no unresolved CRITICAL security finding is deployed unmitigated |
| 11. **Retrospective** | RetroAgent | ReviewMemory, IssueMemory, ObservabilityMemory (this run's metrics), LessonStore | `SprintRetrospective` | Structured retro schema | LessonStore (new lessons), ProjectMemory (metadata) | Retro identifies at least one concrete, actionable lesson; does not simply restate what already happened without an insight |

Workflow terminates after Retrospective is approved (`WorkflowState.Completed`).
