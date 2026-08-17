# AI DevOS — Codebase Map

Generated during Phase 0 understanding.

---

## Full Directory Tree of Python Files (backend/)

```
backend/
├── app/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── architect.py
│   │   ├── backend.py
│   │   ├── base_agent.py
│   │   ├── bug_analyst.py
│   │   ├── clarification.py
│   │   ├── designer.py
│   │   ├── devops.py
│   │   ├── document.py
│   │   ├── factory.py
│   │   ├── file_planner.py
│   │   ├── frontend.py
│   │   ├── integration_developer.py
│   │   ├── product_owner.py
│   │   ├── qa.py
│   │   ├── registry.py
│   │   ├── resolver.py
│   │   ├── retro.py
│   │   ├── scrum_master.py
│   │   ├── security.py
│   │   ├── sprint_deploy.py
│   │   ├── sprint_delta.py
│   │   ├── sprint_planner.py
│   │   ├── sprint_review.py
│   │   ├── strategic_review.py
│   │   ├── tech_lead.py
│   │   └── validation.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── artifacts.py
│   │   ├── auth.py
│   │   ├── analytics.py
│   │   ├── chat.py
│   │   ├── dependencies.py
│   │   ├── exception_handler.py
│   │   ├── files.py
│   │   ├── gates.py
│   │   ├── git.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── rate_limit.py
│   │   │   ├── request_size.py
│   │   │   └── logging_context.py
│   │   └── router.py
│   ├── artifact/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   └── metadata.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── env_writer.py
│   │   ├── loader.py
│   │   ├── manager.py
│   │   ├── models.py
│   │   └── validator.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── startup_validator.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── gate_state.py
│   │   └── users.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── api_contract_extractor.py
│   │   ├── agent_runtime.py
│   │   ├── code_sandbox.py
│   │   ├── engine.py
│   │   ├── execution_metrics.py
│   │   ├── execution_plan.py
│   │   ├── execution_recovery.py
│   │   ├── execution_result.py
│   │   ├── execution_status.py
│   │   ├── execution_validation.py
│   │   ├── exceptions.py
│   │   ├── file_validator.py
│   │   ├── manager.py
│   │   ├── pipeline.py
│   │   ├── preview_manager.py
│   │   ├── project_reader.py
│   │   ├── project_validator.py
│   │   ├── project_writer.py
│   │   ├── recovery_checkpoint.py
│   │   ├── recovery_policy.py
│   │   ├── recovery_result.py
│   │   ├── recovery_validation.py
│   │   ├── runtime_context.py
│   │   ├── runtime_result.py
│   │   ├── runtime_validation.py
│   │   ├── safety_policy.py
│   │   ├── sandbox.py
│   │   ├── scheduler.py
│   │   ├── stage_execution_result.py
│   │   ├── stage_execution_status.py
│   │   ├── stage_executor.py
│   │   ├── stage_validation.py
│   │   └── syntax_validator.py
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── code_summarizer.py
│   │   ├── context_orchestrator.py
│   │   ├── dependency_graph.py
│   │   ├── file_indexer.py
│   │   └── sprint_monitor.py
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── bootstrap.py
│   │   ├── container.py
│   │   ├── health_check.py
│   │   ├── kernel.py
│   │   ├── lifecycle.py
│   │   └── registry.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── llm_validation.py
│   │   └── manager.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── blueprint_store.py
│   │   ├── knowledge_memory.py
│   │   ├── learning_loop.py
│   │   ├── lesson_store.py
│   │   ├── manager.py
│   │   ├── memory_cache.py
│   │   ├── memory_cleanup.py
│   │   ├── memory_context.py
│   │   ├── memory_context_builder.py
│   │   ├── memory_filter.py
117:             include_lessons=True,
118:             lessons_limit=3,
119:             include_patterns=True,
120:             patterns_limit=3,
121:             include_design=False,
122:             include_intelligence=False,
123:             include_clarification=False,
124:         ),
125:     }
126: 
127:     # ------------------------------------------------------------------
128:     # Stage name → budget key  (lowercase → canonical budget key)
128:     # Stage name → budget key  (lowercase → canonical budget key)
128:     # Stage name → budget key  (lowercase → canonical budget key)
129:     _CANONICAL: dict[str, str] = {
130:         "clarification":         "clarification",
131:         "productowner":          "product_owner",
132:         "product_owner":         "product_owner",
133:         "architect":             "architect",
134:         "designer":              "designer",
135:         "backenddeveloper":      "backend",
136:         "backend":               "backend",
137:         "frontenddeveloper":     "frontend",
138:         "frontend":              "frontend",
139:         "qa":                    "qa",
140:         "devops":                "devops",
141:         "document":              "document",
142:         # Aliases for stage names used in constants / enums
143:         "filestructureplanner":  "backend",
144:         "sprintplanning":        "architect",
145:         "scrummaster":           "default",
146:         "security":              "architect",
147:         "buganalyst":            "qa",
148:     }
149: 
150:     @classmethod
151:     def get(cls, stage_name: str) -> ContextBudget:
152:         key = cls._CANONICAL.get(stage_name.lower(), "default")
153:         return cls._BUDGETS[key]
```

---

## Pipeline Execution Order (Stage Names in Sequence)

From `DependencyGraph.STAGE_ORDER` (loaded from config):

**Discovery Phase:**
1. strategic_review
2. clarification  
3. product_owner
4. architect
5. designer
6. security
7. sprint_planner

**Sprint Phase:**
8. scrum_master
9. sprint_delta
10. file_planner
11. backend (BackendDeveloper)
12. frontend (FrontendDeveloper)
13. sprint_deploy
14. sprint_review

**Release Phase:**
15. integration
16. qa
17. bug_analyst
18. devops
19. document
20. retro

---

## Sprint Execution Order (Step Names in Sequence)

From `SprintExecutor.run()`:

1. **ScrumMaster** (non-blocking)
2. **SprintDeltaPlanner** (non-blocking)
3. **FileStructurePlanner** (required)
4. **BackendDeveloper** (parallelizable with FrontendDeveloper)
5. **FrontendDeveloper** (parallelizable with BackendDeveloper)
6. **SandboxVerification** (install → lint → build → test)
7. **SprintDeploy** (via engine)
8. **SprintReview** (via engine)
9. **SprintValidation** (non-blocking)

---

## Agent Class → Primary Action → Output Artifact

| Agent Class | Primary Action / Method | Output Artifact |
|-------------|------------------------|-----------------|
| ArchitectAgent | execute() → write_architecture.py | Architecture spec (modules, api_endpoints, data_models, tech_stack, folder_structure, dependencies, entry_points, constraints) |
| BackendDeveloperAgent | execute_sprint() → write_backend_code.py | Generated backend files per file_plan |
| FrontendDeveloperAgent | execute_sprint() → write_frontend_code.py | Generated frontend files per file_plan + design_artifact |
| FileStructurePlannerAgent | execute() → plan_files.py | FilePlan (generation_order, files map, tech_stack) |
| QAAgent | execute() → write_qa_report.py | Test files (pytest/Jest) |
| DevOpsAgent | execute() → write_deployment.py | Dockerfile, docker-compose.yml, CI/CD |
| DocumentAgent | execute() → write_documentation.py | Documentation |
| ScrumMasterAgent | execute() → write_scrum_plan.py | Sprint task breakdown |
| SprintPlannerAgent | execute() → plan_sprints.py | SprintPlan (sprints with goals/features) |
| SprintDeltaAgent | execute() → write_sprint_delta.py | SprintDeltaArtifact (create/update/patch per file) |
| SprintDeployAgent | deploy_sprint() | Sprint deployment artifacts |
| SprintReviewAgent | review_sprint() | Sprint review summary |
| TechLeadAgent | review() → _TechLeadReviewAction | tech_review.json (approved, violations, missing_files) |
| BugAnalystAgent | execute() → write_bug_analysis.py | Bug report (type: spec_bug/architecture_bug/code_bug) |
| SecurityAgent | execute() → write_security_report.py | Security review |
| ProductOwnerAgent | execute() → write_requirements.py | Product requirements |
| DesignerAgent | execute() → write_design.py | Design spec (components, pages, design_system) |
| ClarificationAgent | execute() → clarify_requirements.py | Clarified requirements |
| StrategicReviewAgent | execute() → write_strategic_brief.py | Strategic brief |
| IntegrationDeveloperAgent | execute() → write_backend_code.py | Integration layer code |
| RetroAgent | execute() → write_retrospective.py | Retrospective |
| DomainResearcherAgent | execute() → domain_research.py | Domain research |
| ValidationAgent | execute() → validation.py | Validation results |
| ChatRouterAgent | execute() | Chat routing |
| DescriptorAgent | execute() | Description |
| FilePlannerAgent | (alias for FileStructurePlanner) | |
| ResolverAgent | execute() | Resolution |

---

## Memory Key Formats

| Key | Purpose | Stored By |
|-----|---------|-----------|
| `design:latest` | Approved DesignArtifact | DesignerAgent |
| `workflow:latest_message` | Most recent AgentMessage | WorkflowEngine._record_message |
| `gate:feedback:architecture` | Architecture gate feedback | Human reviewer |
| `gate:feedback:design` | Design gate feedback | Human reviewer |
| `gate:feedback:sprint_plan` | Sprint plan gate feedback | Human reviewer |
| `blueprint:latest` | BlueprintStore (project_type, folder_structure, etc.) | PipelineSupervisor after Architect |
| `sandbox:latest` | Latest SandboxResult | SprintExecutor._persist_sandbox_result |
| `knowledge_entries` (SQLite + HNSW) | Semantic knowledge store | KnowledgeMemory.store() |
| `lesson_store` | Human-readable lessons | LessonStore |
| `learning_loop` | Past patterns | LearningLoop |
| `project_event_log` | Structured events | ProjectEventLog |
| `memory_context` | Sprint-scoped context | MemoryContextBuilder |

---

## Constants and Config

### STAGE_ORDER (from DependencyGraph)
Loaded from `config/stage_order.yaml` or similar.

### Feature Flags
- `SPRINT_PARALLEL_AGENTS` — parallel backend/frontend (default 1)
- `SPRINT_PARALLEL_FILES` — parallel file generation (default 1)
- `SANDBOX_ENABLED` — code execution sandbox (default false)
- `QUICK_BUILD_MODE` — prototype pipeline (skip stages)

### Model Router Config
- `LLM_PROVIDER` — ollama/openai/anthropic/etc.
- `LLM_MODEL` — model name
- `MODEL_ROUTER_CONFIG` — per-stage model profiles

---

## Key Bugs to Fix (from ai_devos_opencode.md)

### Sprint 1 — P0 Critical
- **B-01**: Hardcoded `backend/` prefix in BackendDeveloperAgent.execute_sprint()
- **B-02**: Hardcoded `frontend/` prefix in FrontendDeveloperAgent.execute_sprint()
- **B-03**: Hardcoded Python/FastAPI persona in BackendDeveloperAgent._file_system_prompt()
- **B-04**: Hardcoded React/Tailwind persona in FrontendDeveloperAgent._file_system_prompt()
- **B-05**: No React Native scaffold step in sprint_executor.py / pipeline_supervisor.py
- **B-19**: ChangeManager=None silently swallows BugAnalyst rollback in pipeline_supervisor.py

### Sprint 2 — P0 Critical
- **B-06**: Context discarded in BackendDeveloperAgent._generate_one_file()
- **B-07**: Context discarded in FrontendDeveloperAgent._generate_one_file()
- **B-30**: sprint_brief always empty in FrontendDeveloperAgent
- **B-20**: REPLANNING doesn't clear release stages from stages_completed

### Sprint 3 — P1 High
- **B-29**: _check_context_window uses cumulative tokens
- **B-15**: CodeSandbox disabled by default; _build_python checks one file
- **B-16**: QA tests never executed (sandbox runs before QA)
- **B-31**: QAAgent.run_sprint_qa() dead code
- **B-22**: Non-atomic SQLite + HNSW write in knowledge_memory.py

### Sprint 4 — P1 High
- **B-27**: FrontendPromptBuilder missing (ImportError)
- **B-08**: _STAGE_NEEDS missing 'backend' for FrontendDeveloper
- **B-11**: _inject_sandbox_results never called in ContextAssembler
- **B-28**: AgentFactory never passes workspace_manager to TechLeadAgent

### Sprint 5 — P2 Medium
- **B-21**: Per-stage token budget never enforced
- **B-09**: WORKFLOW_MESSAGE_KEY overwrites same slot
- **B-10**: predecessor_max_chars too small for BackendDeveloper
- **B-23**: BackendPromptBuilder not used in execute_sprint()
- **B-25**: Architect artifact truncated to 2000 chars
- **B-24**: Architect sizing rules only web-tier

### Sprint 6 — P2/P3
- **B-17**: Mobile QA hardcoded calculator keywords
- **B-32**: _build_mobile_prompt may prepend system prompt
- **B-33**: _WEB_SYSTEM_PROMPT hardcodes FastAPI import
- **B-26**: _inject_template wrong return type annotation