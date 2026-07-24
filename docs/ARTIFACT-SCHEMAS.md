# Artifact Schemas

**Status:** Canonical structured-output schema for every stage artifact, replacing opaque
markdown blobs with typed fields (MetaGPT-derived pattern, research §A4). Each schema is
serialized as JSON (canonical form, stored via `ArtifactManager`) with a Markdown rendering
derived from it for human/reviewer consumption — the JSON is the source of truth, not the
Markdown.

---

### StrategicBrief
*(from StrategicReview stage)*
```yaml
fields:
  - problem_statement: str — the problem restated in the agent's own words
  - scope_mode: enum[Expansion, Selective Expansion, Hold Scope, Reduction] — explicitly chosen, never implied
  - open_questions: List[str] — anything still ambiguous, to be resolved by ProductOwner
  - non_goals: List[str] — explicitly out of scope for this run
  - anything_unclear: str
example: |
  {
    "problem_statement": "Users cannot recover their account after losing 2FA access.",
    "scope_mode": "Hold Scope",
    "open_questions": ["Should recovery require identity verification beyond email?"],
    "non_goals": ["Passwordless login redesign"],
    "anything_unclear": ""
  }
```

### ProductRequirements
*(from ProductOwner — PRD format, MetaGPT-derived)*
```yaml
fields:
  - language: str
  - programming_language: str
  - original_requirements: str
  - project_name: str
  - product_goals: List[str] — max 3
  - user_stories: List[str] — 3-5
  - competitive_analysis: List[str] — 5-7
  - competitive_quadrant_chart: str — mermaid quadrantChart syntax
  - requirement_analysis: str
  - requirement_pool: List[Tuple[priority, requirement]] — top 5
  - ui_design_draft: str
  - anything_unclear: str
example: |
  {
    "language": "en_us",
    "programming_language": "Python, FastAPI, React",
    "original_requirements": "Users cannot recover their account after losing 2FA access.",
    "project_name": "account_recovery",
    "product_goals": ["Reduce support tickets", "Secure recovery flow", "Fast resolution"],
    "user_stories": ["As a user who lost my 2FA device, I want to recover my account via verified email so I can regain access."],
    "competitive_analysis": ["Auth0 recovery flow", "Okta recovery flow"],
    "competitive_quadrant_chart": "quadrantChart\n  title Reach and engagement",
    "requirement_analysis": "Recovery must not weaken existing 2FA guarantees.",
    "requirement_pool": [["P0", "Email-verified recovery flow"]],
    "ui_design_draft": "Single-page recovery form with step indicator.",
    "anything_unclear": ""
  }
```

### SystemArchitecture
*(from Architect, MetaGPT-derived)*
```yaml
fields:
  - implementation_approach: str
  - file_list: List[str] — relative paths, entry file first
  - data_structures_and_interfaces: str — mermaid classDiagram
  - program_call_flow: str — mermaid sequenceDiagram
  - anything_unclear: str
example: |
  {
    "implementation_approach": "FastAPI backend, React frontend, PostgreSQL storage.",
    "file_list": ["backend/app/main.py", "backend/app/auth/recovery.py"],
    "data_structures_and_interfaces": "classDiagram\n  class RecoveryRequest",
    "program_call_flow": "sequenceDiagram\n  User->>API: POST /recovery",
    "anything_unclear": ""
  }
```

### SecurityReport
*(from SecurityAgent, gstack CSO-derived)*
```yaml
fields:
  - phases_run: List[str] — which audit phases executed
  - findings: List[Finding] where Finding = {
      severity: enum[CRITICAL, HIGH, MEDIUM, LOW],
      category: str,
      description: str,
      exploit_scenario: str,
      remediation: str,
      confidence: int (1-10)
    }
  - suppressed_low_confidence_count: int
  - overall_posture: enum[BLOCKING, ACCEPTABLE_WITH_FOLLOWUP, CLEAR]
example: |
  {
    "phases_run": ["secrets_archaeology", "owasp_top_10"],
    "findings": [
      {"severity": "CRITICAL", "category": "secrets", "description": "Hardcoded API key",
       "exploit_scenario": "Key committed to public repo enables full account takeover.",
       "remediation": "Move to secret manager, rotate key.", "confidence": 9}
    ],
    "suppressed_low_confidence_count": 2,
    "overall_posture": "BLOCKING"
  }
```

### TaskPlan
*(from Planner)*
```yaml
fields:
  - tasks: List[Task] where Task = {
      task_id: str ("TASK-001" sequential),
      title: str,
      description: str,
      depends_on: List[str] — other task_ids,
      estimated_complexity: enum[S, M, L]
    }
  - milestones: List[str]
example: |
  {
    "tasks": [
      {"task_id": "TASK-001", "title": "Recovery request endpoint", "description": "...",
       "depends_on": [], "estimated_complexity": "M"}
    ],
    "milestones": ["Backend recovery flow complete"]
  }
```

### BackendCode
*(from BackendDeveloper)*
```yaml
fields:
  - files: List[FileChange] where FileChange = {path: str, content: str, change_type: enum[create, modify]}
  - summary: str
  - completed_task_ids: List[str]
  - incomplete_task_ids: List[str]
example: |
  {
    "files": [{"path": "backend/app/auth/recovery.py", "content": "...", "change_type": "create"}],
    "summary": "Implemented recovery request/verify endpoints.",
    "completed_task_ids": ["TASK-001"],
    "incomplete_task_ids": []
  }
```

### FrontendCode
*(from FrontendDeveloper)*
```yaml
fields:
  - files: List[FileChange] — same shape as BackendCode
  - summary: str
  - api_contract_version_used: str — which BackendCode artifact version this was built against
example: |
  {
    "files": [{"path": "frontend/src/pages/Recovery.tsx", "content": "...", "change_type": "create"}],
    "summary": "Recovery form with step indicator.",
    "api_contract_version_used": "BackendCode-v1"
  }
```

### QAReport
*(from QA, gstack-derived)*
```yaml
fields:
  - health_score: int (0-100)
  - category_scores: Dict[str, int] — Console, Links, Visual, Functional, UX, Performance, Accessibility
  - top_fixes: List[str] — max 3
  - fixes_applied: List[{issue: str, fix: str, regression_test: str}]
  - ship_readiness: enum[READY, READY_WITH_CAVEATS, NOT_READY]
example: |
  {
    "health_score": 92,
    "category_scores": {"Functional": 95, "Accessibility": 85},
    "top_fixes": ["Fixed missing loading state on recovery submit"],
    "fixes_applied": [{"issue": "No loading state", "fix": "Added spinner", "regression_test": "test_recovery_loading_state"}],
    "ship_readiness": "READY"
  }
```

### DocumentationUpdate
*(from DocumentAgent)*
```yaml
fields:
  - affected_docs: List[str]
  - changes: List[{doc: str, diff: str}]
example: |
  {
    "affected_docs": ["docs/API.md"],
    "changes": [{"doc": "docs/API.md", "diff": "+ POST /recovery/request\n+ POST /recovery/verify"}]
  }
```

### DeploymentConfig
*(from DevOps)*
```yaml
fields:
  - manifest_files: List[FileChange]
  - environment_variables: List[str] — names only, never values/secrets
  - unmitigated_critical_findings: List[str] — must be empty to deploy
example: |
  {
    "manifest_files": [{"path": "Dockerfile", "content": "...", "change_type": "create"}],
    "environment_variables": ["DATABASE_URL", "OLLAMA_HOST"],
    "unmitigated_critical_findings": []
  }
```

### SprintRetrospective
*(from RetroAgent)*
```yaml
fields:
  - what_worked: List[str]
  - what_failed: List[str]
  - lessons_recorded: List[str] — keys of LessonStore entries written this run
  - metrics_summary: {avg_retries: float, total_llm_calls: int, total_duration_s: int}
example: |
  {
    "what_worked": ["Security review before planning caught the missing rate-limit requirement early."],
    "what_failed": ["Frontend agent initially assumed a different API shape than BackendCode produced."],
    "lessons_recorded": ["frontend-must-read-backend-artifact"],
    "metrics_summary": {"avg_retries": 1.2, "total_llm_calls": 14, "total_duration_s": 340}
  }
```
