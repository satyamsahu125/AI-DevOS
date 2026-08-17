# AI DevOS — OpenCode Bug-Fix Loop Prompt

You are a senior software engineer tasked with fixing all known bugs in the AI DevOS codebase.
You will work autonomously in a loop: understand → fix → test → log → repeat, until every bug is resolved.

---

## ABSOLUTE RULES — READ BEFORE TOUCHING ANY FILE

These rules are non-negotiable. Violating them causes more damage than the bugs themselves.

### Scope Rules
1. **Fix only the bug you are currently working on.** Do not refactor surrounding code, rename variables, reformat files, or "improve" unrelated logic.
2. **Touch only the files listed in the bug's "File / Component" field.** If a fix requires touching a file not in that list, stop and log it as a blocker — do not expand scope.
3. **Do not create new files unless the bug explicitly requires it** (e.g., B-27 requires creating `frontend_builder.py`). Document every new file created.
4. **Do not change public method signatures** unless the bug explicitly requires it. Adding a parameter must keep the old default so nothing breaks.
5. **Do not remove existing functionality.** If you are unsure whether a code path is used, keep it and add the new behavior alongside it.
6. **Do not fix two bugs in one edit.** One bug → one isolated commit. If you spot another bug while fixing the current one, log it in `FIX_LOG.md` and move on.

### Code Rules
7. **Never assume undocumented behavior.** Read the actual method body before assuming what it does.
8. **Never invent APIs, classes, or methods.** If you need a method, check that it exists first. If it does not exist, log a blocker — do not create placeholder stubs.
9. **Every change must be minimal.** The smallest correct change wins over a larger "clean" one.
10. **Preserve all existing imports.** Do not remove unused-looking imports — they may be used at runtime or in test paths you cannot see.
11. **Never hallucinate framework behavior.** If you are unsure how a library works, read its usage elsewhere in the codebase before proceeding.

### Testing Rules
12. **After every single fix, run sanity tests before moving to the next bug.** If any test fails that was passing before, revert the fix and log the failure.
13. **A fix is not complete until sanity tests pass.** Do not mark a bug as Fixed in the log if tests are failing.
14. **Do not modify test files to make tests pass.** If a test breaks and the fix is correct, investigate why — do not adjust the test.

### Architectural Rules (AI DevOS Core Principles — Never Violate)
15. **Agents are stateless.** Never add instance-level mutable state to an agent class.
16. **Workflow Engine is the only orchestrator.** Agents must not call other agents directly.
17. **No direct agent-to-agent communication.** Communication only through artifacts and memory.
18. **Execution Engine is the only component allowed to modify project files.**
19. **Every stage produces structured artifacts.** If a method produces output, it must be written to the ArtifactStore or MemoryManager.
20. **Context Builder constructs context.** ContextAssembler owns context construction — no agent builds its own full context independently.

---

## PHASE 0 — CODEBASE UNDERSTANDING (Do this ONCE before any fix)

You must understand the codebase before writing a single line. Complete every step. Do not skip. then check FIX_LOG.md file to waht have fixed.

### Step 0.1 — Map the directory structure
```
List every .py file in backend/ recursively, grouped by subdirectory.
Do not read any file that is not in this list.
```

### Step 0.2 — Read the entry point
Read `backend/app/main.py` (or wherever the FastAPI app is created).
Map every API endpoint: HTTP method, path, what handler it calls.

### Step 0.3 — Understand the pipeline execution flow
Read these files fully, in this order:
1. `backend/app/workflow/pipeline_supervisor.py` — how stages are sequenced
2. `backend/app/workflow/engine.py` — how a single stage executes
3. `backend/app/workflow/stage_runner.py` — how retry/context-window logic works
4. `backend/app/workflow/context_assembler.py` — how context is built
5. `backend/app/execution/sprint_executor.py` (if it exists) — how sprints run

### Step 0.4 — Understand the agent layer
Read every file in `backend/app/agents/`.
For each agent, note: class name, primary action, whether it has execute_sprint() vs execute().

### Step 0.5 — Understand the prompt layer
Read every file in `backend/app/prompt/`.
For each builder, note: which stage it serves, what keys it reads from context.

### Step 0.6 — Understand the memory layer
Read every file in `backend/app/memory/`.
Note: what each class stores, what backend it uses (SQLite/in-memory/file).

### Step 0.7 — Read the constants and config
Read `backend/app/shared/constants.py` and any `.yaml` or `.json` config in the project root.
Note: STAGE_ORDER, any feature flags, model router config.

### Step 0.8 — Create your understanding map
After reading, write a file called `CODEBASE_MAP.md` in the project root with:
- Full directory tree of Python files
- Pipeline execution order (stage names in sequence)
- Sprint execution order (step names in sequence)  
- Every agent class → its primary action → its output artifact
- Every known memory key format

**Do not start Phase 1 until this map is written.**

---

## PHASE 1 — INITIALIZE THE FIX LOG

Before your first fix, create `FIX_LOG.md` in the project root with this exact structure:

```markdown
# AI DevOS — Bug Fix Log
Generated by: OpenCode autonomous fix session
Started: [timestamp]

## Summary
- Total bugs: 33
- Fixed: 0
- Blocked: 0
- Skipped: 0
- In Progress: 0

## Fix History
(entries appended after each fix)

## Blocked Bugs
(entries added when a blocker is found)
```

After every fix attempt, update FIX_LOG.md:
- Increment the correct counter in Summary
- Append a Fix History entry (format below)
- If blocked, add to Blocked Bugs section

### Fix History Entry Format
```markdown
### [BUG-ID] — [STATUS: Fixed | Blocked | Skipped]
- **Date**: [timestamp]
- **File(s) changed**: [exact file paths]
- **What was wrong**: [one sentence quoting the bad code]
- **What was fixed**: [one sentence describing the change]
- **Sanity test result**: [PASS | FAIL — and which test failed]
- **Lines changed**: [approximate line numbers]
```

### Blocked Bug Entry Format
```markdown
### [BUG-ID] — BLOCKED
- **Reason**: [exact reason — missing dependency, callee not found, etc.]
- **Missing**: [what file or method is needed]
- **Unblocked by**: [which other bug, if known]
```

---

## PHASE 2 — FIX LOOP

Work through bugs in the exact priority order listed below. Do not reorder.
For each bug: read → understand → fix → test → log → next.

### For each bug, follow this exact sequence:

```
STEP A — RE-READ THE TARGET FILE(S)
  Read the exact file(s) listed in the bug. Do not rely on memory from Phase 0.
  Find the exact method and line range named in the bug.
  Confirm the bug exists as described. If it does not exist (already fixed), log as Skipped.

STEP B — FORM YOUR FIX PLAN
  State in one sentence: "I will change [method] in [file] to [specific change]."
  State what you will NOT touch: "I will not change [x, y, z]."
  If your fix requires touching a file not in the bug's scope, STOP — log as Blocked.

STEP C — IMPLEMENT
  Make the minimal change. One logical edit. No style changes. No refactoring.

STEP D — VERIFY YOUR OWN CHANGE
  Read the changed lines back. Confirm the bug pattern is gone.
  Confirm you have not introduced any new import that doesn't exist.
  Confirm all callee methods you call actually exist in the codebase.

STEP E — RUN SANITY TESTS
  Run: python -m pytest backend/tests/ -x -q --tb=short
  If no tests directory exists: run python -m py_compile on every changed file.
  If tests fail: revert the change, log as Blocked with the failure output.

STEP F — UPDATE FIX_LOG.md
  Append the Fix History entry. Update the summary counters.
```

---

## BUG LIST — ORDERED BY PRIORITY

Work through these in order. Do not skip ahead.

---

### SPRINT 1 — P0 CRITICAL (Fix These First)

---

**B-01** — Mobile File Routing: Hardcoded `backend/` prefix filter in BackendDeveloperAgent
- File: `backend/app/agents/backend.py`
- Method: `execute_sprint()`
- Bug: The file filter inside execute_sprint() uses a hardcoded prefix condition that keeps only files starting with `backend/`. Any non-Python project (React Native, Android, Go, ML) gets zero backend files generated with no error.
- Fix: Read the filter condition. Replace the hardcoded prefix string with a lookup against `project_type` from the context. Map: `python/fastapi → backend/`, `mobile/react_native → app/`, `go → cmd/ or internal/`, `android → app/src/`. If project_type is unknown, allow all paths and log a warning.
- Scope guard: Change only the filter condition inside execute_sprint(). Do not touch `_generate_one_file()`, `_build_file_prompt()`, or any other method.

---

**B-02** — Mobile File Routing: Hardcoded `frontend/` prefix filter in FrontendDeveloperAgent
- File: `backend/app/agents/frontend.py`
- Method: `execute_sprint()`
- Bug: Identical to B-01 but for frontend. Hardcoded `frontend/` prefix drops all React Native paths (app/, App.tsx, screens/).
- Fix: Same approach as B-01. Map: `web → frontend/`, `mobile/react_native → app/ or screens/ or components/`. Allow all if unknown.
- Scope guard: Change only the filter condition. Do not touch design_artifact handling or _build_file_prompt().

---

**B-03** — Hardcoded Python/FastAPI system prompt persona in BackendDeveloperAgent
- File: `backend/app/agents/backend.py`
- Method: `_file_system_prompt()`
- Bug: System prompt hardcodes "You are an expert Python/FastAPI backend developer" for ALL project types.
- Fix: Read `project_type` from the context object passed in. Build a persona lookup dict: `{"python": "Python/FastAPI", "go": "Go", "kotlin": "Kotlin/Android", "rust": "Rust", "react_native": "React Native/TypeScript"}`. Return the matching persona string interpolated into the system prompt prefix. Default to "Python/FastAPI" only when project_type is None.
- Scope guard: Change only `_file_system_prompt()`. Do not add new methods.

---

**B-04** — Hardcoded React/Tailwind system prompt in FrontendDeveloperAgent
- File: `backend/app/agents/frontend.py`
- Method: `_file_system_prompt()`
- Bug: Hardcodes "React/TypeScript + Tailwind CSS" for ALL frontend types. Tailwind is incompatible with React Native.
- Fix: Same pattern as B-03. For `mobile/react_native`: substitute "React Native/TypeScript with StyleSheet/NativeWind". For web: keep Tailwind. For unknown: use web defaults.
- Scope guard: Change only `_file_system_prompt()`.

---

**B-05** — No scaffold step for React Native mandatory entry-point files
- File: `backend/app/execution/sprint_executor.py` (or pipeline_supervisor.py — read both to find where post-sprint steps are added)
- Bug: No generation step creates App.tsx, babel.config.js, tsconfig.json, metro.config.js for React Native projects.
- Fix: After all sprint dev agents complete, check if `project_type == "react_native"` (or "mobile"). If yes, write the four scaffold files with safe minimal content. Do not overwrite if they already exist. Write via the existing file-write mechanism used by other agents — do not write files directly.
- Scope guard: Add only a post-sprint conditional block. Do not alter the sprint loop itself.

---

**B-19** — ChangeManager=None silently swallows BugAnalyst rollback requests
- File: `backend/app/workflow/pipeline_supervisor.py`
- Method: The BugAnalyst rollback handler (search for `change_manager` in the file)
- Bug: `change_manager=None` by default. When BugAnalyst triggers a rollback, the code logs a warning and sets state but does not invalidate any stages.
- Fix: First check if ChangeManager is actually injected into `__init__()`. If `change_manager` is not a parameter: add it as an optional parameter with default None. In the rollback handler: if `change_manager is None`, raise a RuntimeError with message "ChangeManager not injected — cannot perform rollback. Wire ChangeManager in PipelineSupervisor." Do not silently ignore. The fail-loud behavior is correct here.
- Scope guard: Change only the rollback handler and `__init__` signature. Do not touch any other state transition logic.

---

### SPRINT 2 — P0 CRITICAL (Fix After Sprint 1)

---

**B-06** — Context discarded in BackendDeveloperAgent file generation
- File: `backend/app/agents/backend.py`
- Method: `_generate_one_file()` and its call in `execute_sprint()`
- Bug: The assembled context object is passed into execute_sprint() but NEVER forwarded to `_build_file_prompt()`. The context arg to _build_file_prompt() is always ignored or replaced with "".
- Fix: Find the call to `_build_file_prompt()` inside `_generate_one_file()`. Read `_build_file_prompt()`'s signature. Add the context as a parameter if not already present. Inside `_build_file_prompt()`, extract these sections from context (use getattr with defaults): architect summary, API contracts, predecessor message. Append them to the user prompt under a clearly labeled section header.
- Scope guard: Change only `_generate_one_file()` and `_build_file_prompt()`. Do not change execute_sprint().

---

**B-07** — Identical context-discard bug in FrontendDeveloperAgent
- File: `backend/app/agents/frontend.py`
- Method: `_generate_one_file()` and `_build_file_prompt()`
- Bug: Identical to B-06. Context is accepted but not forwarded.
- Fix: Identical approach to B-06. Additionally inject the backend API contracts section if available in context (check for `backend_artifacts` or similar key).
- Scope guard: Same as B-06 — only these two methods.

---

**B-30** — FrontendDeveloperAgent sprint_brief always empty string
- File: `backend/app/agents/frontend.py`
- Method: `execute_sprint()` call to `_build_file_prompt()`
- Bug: execute_sprint() receives `sprint_brief` parameter but passes `""` to `_build_file_prompt()`.
- Fix: Pass `sprint_brief` through to `_build_file_prompt()`. Read `_build_file_prompt()`'s signature — if `sprint_brief` parameter doesn't exist there, add it with default `""`. Inject it into the user prompt under a "SPRINT SCOPE" section header.
- Scope guard: This is the same file as B-07. Verify B-07 is already fixed before touching this. Change only the argument at the call site and the _build_file_prompt signature/body.

---

**B-20** — REPLANNING block does not clear release stages from stages_completed
- File: `backend/app/workflow/pipeline_supervisor.py`
- Method: `_run_impl()` REPLANNING block
- Bug: When REPLANNING sets state to ALL_SPRINTS_COMPLETE, release stages are not removed from `stages_completed`, so they are immediately skipped as already done.
- Fix: Find the REPLANNING block. After setting the state, add: identify which keys in `stages_completed` correspond to release stages (read how stages_completed is keyed — by stage name string or enum). Remove those keys. Log which stages were cleared.
- Scope guard: Change only the REPLANNING block. Do not touch Discovery or Sprint blocks.

---

### SPRINT 3 — P1 HIGH

---

**B-29** — _check_context_window() uses cumulative project tokens instead of per-call count
- File: `backend/app/workflow/engine.py`
- Method: `_check_context_window()`
- Bug: The method compares `total_project_tokens` (a cumulative counter) against a per-call context window limit. After a few stages it permanently fires.
- Fix: Read the full method. Find where `total_project_tokens` is accumulated and where the comparison is made. Add a separate counter `current_call_tokens` that is reset to 0 at the start of each stage's execution. Count only the tokens for the current call. Compare `current_call_tokens` against the limit.
- Scope guard: Change only `_check_context_window()` and the token-counting call site for the current call. Do not change how total_project_tokens is tracked elsewhere.

---

**B-15** — CodeSandbox disabled by default; _build_python() checks only one file
- File: `backend/app/execution/code_sandbox.py`
- Bug (two parts):
  - Part 1: `SANDBOX_ENABLED=false` in environment/config — syntax_check() returns empty list when disabled.
  - Part 2: `_build_python()` only py_compiles ONE entry-point file, leaving all other .py files unchecked.
- Fix Part 1: Find the env var check. Change the default to `True`. If this is in an `.env.example` file, note it but only change the Python code default.
- Fix Part 2: Find `_build_python()`. Change it to compile ALL `.py` files in the project directory (use glob or os.walk). Preserve the existing single-file behavior as a fallback if globbing fails.
- Scope guard: Change only code_sandbox.py. Do not touch pipeline_supervisor.py sandbox call sites.

---

**B-16** — QA-generated test files never executed (sandbox runs before QA writes tests)
- File: `backend/app/workflow/pipeline_supervisor.py`
- Method: The Release phase execution block (search for where QA stage and sandbox run are called)
- Bug: Sandbox runs before the QA release stage. QA writes test files during release. Those new files never run.
- Fix: Find the Release phase block. Verify the order: if sandbox call comes BEFORE QA stage call, swap their order. If they are separate methods, ensure sandbox is called again AFTER QA completes. Add a log message: "Running sandbox with QA-generated test files."
- Scope guard: Change only the ordering in the Release phase. Do not change the sandbox or QA implementations themselves.

---

**B-31** — QAAgent.run_sprint_qa() is dead code — never called in sprint execution
- File: `backend/app/execution/sprint_executor.py` (read it first to find current step order)
- Bug: run_sprint_qa() is implemented but no call exists in the sprint execution loop.
- Fix: Read sprint_executor.py. Find where BackendDeveloperAgent and FrontendDeveloperAgent are called. After both complete, add a call to the QA agent's sprint QA method. Obtain the QA agent instance the same way the dev agents are obtained (through the factory or direct instantiation — match the existing pattern). Pass the same context.
- Scope guard: Add only the new call in sprint_executor.py. Do not modify QAAgent or its run_sprint_qa() implementation.

---

**B-22** — Non-atomic SQLite + HNSW write in knowledge_memory.py
- File: `backend/app/memory/knowledge_memory.py`
- Method: `store()`
- Bug: `conn.commit()` and `_save_index()` are sequential, not atomic. A crash between them corrupts the store.
- Fix: Wrap the sequence in try/except. If `_save_index()` raises: catch the exception, roll back the SQLite transaction (call `conn.rollback()`), re-raise the exception so the caller knows the write failed. Add a log.error call before re-raising.
- Scope guard: Change only the `store()` method. Do not change `_save_index()` or the SQLite connection setup.

---

**B-27** — FrontendPromptBuilder missing (ImportError when FrontendDeveloperAgent is instantiated)
- File to create: `backend/app/prompt/frontend_builder.py`
- Bug: `agents/frontend.py` imports `FrontendPromptBuilder` from `..prompt.frontend_builder`, which does not exist.
- Fix: Create `frontend_builder.py`. Model it directly after `backend_builder.py` — read that file first. Create a `FrontendPromptBuilder` class with at minimum: `build_system_prompt(project_type: str) -> str` method that returns a web persona for `web`/`fullstack`, a React Native persona for `mobile`/`react_native`, and the default web persona for unknown types. Do not invent complex logic — mirror the structure of backend_builder exactly.
- Scope guard: Only create `frontend_builder.py`. Do not modify `frontend.py` or any other file.

---

### SPRINT 4 — P1 HIGH

---

**B-08** — FrontendDeveloper _STAGE_NEEDS missing 'backend' entry
- File: `backend/app/intelligence/context_orchestrator.py`
- Bug: `_STAGE_NEEDS` dict for 'FrontendDeveloper' does not include 'backend' or 'BackendDeveloper'. Frontend never receives backend API contracts.
- Fix: Find `_STAGE_NEEDS`. Add `'backend'` (or whatever key the backend stage uses — read the dict to see the key format) to the FrontendDeveloper entry. Do not change any other entry.
- Scope guard: Change only the `_STAGE_NEEDS` dict. One line change.

---

**B-11** — _inject_sandbox_results() never called in ContextAssembler.assemble()
- File: `backend/app/workflow/context_assembler.py`
- Method: `assemble()`
- Bug: `_inject_sandbox_results()` is implemented and correct but assemble() never calls it.
- Fix: Read the full `assemble()` method. Find where `_inject_gate_feedback()` and `_inject_template()` are called. Add a call to `_inject_sandbox_results(project_id, stage_name, base)` BEFORE `_inject_template()`. Read `_inject_sandbox_results()`'s signature first to pass exactly the right arguments. Do not guess — read the method.
- Scope guard: Add only one call in assemble(). Do not change _inject_sandbox_results() implementation.

---

**B-28** — AgentFactory never passes workspace_manager to TechLeadAgent
- File: `backend/app/agents/agent_factory.py`
- Method: `create()` — the TechLead branch
- Bug: AgentFactory.create() for TechLeadAgent never passes workspace_manager. TechLeadAgent always gets None.
- Fix: Read the factory's create() method. Find the TechLead branch. Read TechLeadAgent.__init__() signature to confirm the parameter name is `workspace_manager`. Add the injection: look at how other agents receive workspace_manager from the factory and use the same pattern.
- Scope guard: Change only the TechLead branch of create(). Do not touch any other agent branch.

---

### SPRINT 5 — P2 MEDIUM

---

**B-21** — Per-stage token budget never enforced in ContextAssembler
- File: `backend/app/workflow/context_assembler.py`
- Method: `assemble()`
- Bug: `ContextBudgetRegistry` per-stage `max_total_tokens` limits are never applied. Only a global 600k-char cap exists in StageRunner.
- Fix: At the END of assemble(), after all context is built, call `ContextBudgetRegistry.get(stage_name)` to retrieve the budget for this stage. If `budget.max_total_tokens` is set, compute `max_chars = budget.max_total_tokens * 4`. If `len(assembled_context) > max_chars`, trim to max_chars. Log a warning with how many chars were trimmed.
- Scope guard: Add only the trim block at the end of assemble(). Do not change any individual enrichment method.

---

**B-09** — WORKFLOW_MESSAGE_KEY overwrites same slot on every stage
- File: `backend/app/workflow/engine.py`
- Method: `_record_message()`
- Bug: A single constant key overwrites the same memory slot, losing all but the last stage's output.
- Fix: Read `_record_message()`. Change the key from `WORKFLOW_MESSAGE_KEY` to `f"{WORKFLOW_MESSAGE_KEY}:{stage_name}"` where `stage_name` is the current stage. Verify the stage name is available in that method's scope. Also keep writing to the constant key for backward compatibility (so nothing that reads WORKFLOW_MESSAGE_KEY breaks immediately).
- Scope guard: Change only `_record_message()`. One or two lines.

---

**B-10** — predecessor_max_chars too small for BackendDeveloper (truncates Architect output)
- File: `backend/app/workflow/context_budget.py`
- Bug: BackendDeveloper's `predecessor_max_chars=1000` truncates the Architect artifact (typically 5,000–10,000 chars).
- Fix: Find the BackendDeveloper budget entry. Increase `predecessor_max_chars` to 6000. Do the same for FrontendDeveloper if its value is also ≤ 2000. Do not change any other budget entry.
- Scope guard: Change only BackendDeveloper (and optionally FrontendDeveloper) predecessor_max_chars. One or two value changes.

---

**B-23** — BackendPromptBuilder not used in execute_sprint() (dead code path)
- File: `backend/app/agents/backend.py`
- Method: `_file_system_prompt()`
- Bug: The project-type-aware BackendPromptBuilder exists in prompt/backend_builder.py but `_file_system_prompt()` hardcodes Python/FastAPI instead of using it.
- Pre-check: Confirm B-03 is already fixed. B-23 replaces the B-03 fix with a more complete solution using BackendPromptBuilder.
- Fix: Import `BackendPromptBuilder` from `..prompt.backend_builder`. In `_file_system_prompt()`, call `BackendPromptBuilder().build_system_prompt(project_type)` and return its result. Remove the project_type lookup dict added in B-03 — BackendPromptBuilder now owns that logic.
- Scope guard: Change only `_file_system_prompt()`. Update the import block.

---

**B-25** — Architect artifact truncated to 2,000 chars in ContextOrchestrator
- File: `backend/app/intelligence/context_orchestrator.py`
- Method: `_load_stage_artifacts()`
- Bug: Architect artifact truncated to 2,000 chars; full spec is 5,000–10,000 chars.
- Fix: Find the truncation line for the Architect artifact. Read the code to confirm the limit is a hardcoded integer or a constant. Increase it to 8000 for the Architect stage only. Do not change limits for other stages.
- Scope guard: Change only the Architect truncation value. One value change.

---

**B-24** — Architect sizing rules describe only web-tier infrastructure
- File: `backend/app/prompt/architect_builder.py`
- Method: The SYSTEM_PROMPT string — ARCHITECTURE SIZING RULES section
- Bug: Sizing rules describe FastAPI/PostgreSQL/Redis/CDN patterns only. No mobile, ML, or CLI patterns.
- Fix: Read the ARCHITECTURE SIZING RULES section. After the existing web-tier rules, add new subsections for: mobile (app store distribution, push notification infra, local SQLite/async-storage), ML (GPU compute, dataset storage, model registry), CLI (binary packaging, platform distribution). Keep the existing web rules unchanged.
- Scope guard: Append only to the ARCHITECTURE SIZING RULES section of SYSTEM_PROMPT. Do not change any other part of architect_builder.py.

---

### SPRINT 6 — P2/P3

---

**B-17** — Mobile QA file filter has hardcoded calculator keywords + calculator test template
- File: `backend/app/prompt/qa_builder.py`
- Methods: `_build_mobile_prompt()` and `_MOBILE_SYSTEM_PROMPT`
- Bug: `_MOBILE_SYSTEM_PROMPT` references calculator.test.ts, memory.test.ts, CalculatorScreen.test.tsx. The file filter includes 'calculator' and 'math' keywords.
- Fix:
  - Part 1: In `_MOBILE_SYSTEM_PROMPT`, replace calculator-specific test file names with generic placeholders: `__tests__/[ScreenName].test.tsx`, `__tests__/[ServiceName].test.ts`. Remove all calculator-specific terminology.
  - Part 2: In the file filter keyword list, remove 'calculator' and 'math'. Replace with generic screen/service detection based on the project's actual file names passed in context.
- Scope guard: Change only `_MOBILE_SYSTEM_PROMPT` string and the keyword filter list. Do not change any other method.

---

**B-32** — _build_mobile_prompt() may prepend system prompt into user message (CALLEE-UNVERIFIED)
- File: `backend/app/prompt/qa_builder.py`
- Method: `_build_mobile_prompt()`
- Pre-check: Read the method. Verify whether it actually concatenates system prompt into the user message body. If it does not, log as Skipped with evidence.
- Bug: If confirmed: system prompt prepended into user message instead of being passed as separate parameter.
- Fix (if confirmed): Change the return value to a tuple `(system_prompt_str, user_prompt_str)`. Update the caller to unpack the tuple and pass each to the correct generate_text() parameter. Read the caller first to confirm its signature.
- Scope guard: Change only _build_mobile_prompt() and its direct caller. Do not touch _build_web_prompt().

---

**B-33** — _WEB_SYSTEM_PROMPT hardcodes FastAPI import path and auth endpoint
- File: `backend/app/prompt/qa_builder.py`
- Bug: `_WEB_SYSTEM_PROMPT` hardcodes `from backend.main import create_app` and `/api/v1/auth/register`.
- Fix: Read `_WEB_SYSTEM_PROMPT`. Find the hardcoded import and endpoint. Replace them with generic placeholders: `from {app_module} import {app_factory}` and `{auth_endpoint}`. These should be filled in dynamically based on the web framework detected from context. If dynamic injection is too complex (requires understanding how _WEB_SYSTEM_PROMPT is built), at minimum: remove the hardcoded FastAPI import and replace with a comment "# import your app factory here" and change the hardcoded endpoint to a variable reference `{BASE_URL}/auth/login`.
- Scope guard: Change only the hardcoded strings in _WEB_SYSTEM_PROMPT. Do not restructure the method.

---

**B-26** — _inject_template() wrong return type annotation
- File: `backend/app/workflow/context_assembler.py`
- Method: `_inject_template()`
- Bug: Return type annotation says `tuple[str, bool]` but method returns 4 values.
- Fix: Read the method signature and return statement. Fix the annotation to `tuple[str, bool, str | None, float | None]`. No logic change — annotation only.
- Scope guard: Change only the type annotation. One line.

---

## PHASE 3 — FINAL VERIFICATION

After all bugs are fixed or blocked, run this verification pass:

### 3.1 — Full test suite
```bash
python -m pytest backend/tests/ -v --tb=short 2>&1 | tee test_results.txt
```

### 3.2 — Import check (catch missing-module errors)
```bash
python -c "
import backend.app.agents.backend
import backend.app.agents.frontend
import backend.app.agents.tech_lead
import backend.app.agents.agent_factory
import backend.app.workflow.engine
import backend.app.workflow.context_assembler
import backend.app.workflow.pipeline_supervisor
import backend.app.prompt.qa_builder
import backend.app.prompt.architect_builder
import backend.app.prompt.frontend_builder
import backend.app.memory.knowledge_memory
import backend.app.execution.code_sandbox
print('All imports OK')
"
```

### 3.3 — Compile all Python files
```bash
python -m compileall backend/ -q
```

### 3.4 — Update FIX_LOG.md with final status
Update the Summary section with final counts.
Add a "Final Verification" section:
```markdown
## Final Verification
- Test suite: [PASS/FAIL — N tests, N failures]
- Import check: [PASS/FAIL]
- Compile check: [PASS/FAIL]
- Total bugs Fixed: N
- Total bugs Blocked: N  
- Total bugs Skipped: N (with reasons)
```

---

## PHASE 4 — FINAL REPORT

After verification, produce a summary report. Append it to `FIX_LOG.md` as a new section:

```markdown
## Fix Session Report — Final

### Fixed Bugs (copy from Fix History)
| Bug ID | File | What Changed | Lines |
|--------|------|--------------|-------|
...

### Blocked Bugs (need manual review)
| Bug ID | Reason | What Is Needed |
|--------|--------|----------------|
...

### Skipped Bugs (already fixed or not confirmed)
| Bug ID | Reason |
|--------|--------|
...

### Architectural Integrity Check
For each AI DevOS principle, confirm it is still upheld:
- [ ] Agents are stateless
- [ ] Workflow Engine is only orchestrator
- [ ] No direct agent-to-agent communication
- [ ] Execution Engine owns file writes
- [ ] Every stage produces structured artifacts
- [ ] Context Builder constructs context
- [ ] Memory Manager stores/retrieves memory
- [ ] Reviewer approves every stage
```

---

## WHAT NOT TO DO — ANTI-PATTERNS

These actions are explicitly forbidden regardless of how "clean" they seem:

| Anti-Pattern | Why Forbidden |
|---|---|
| Fixing related bugs in one edit | Breaks isolation; impossible to revert one without reverting both |
| Removing `# TODO` comments | They document intent; removing them loses information |
| Upgrading library imports to newer APIs | May break other callers; not in scope |
| Adding logging to every method | Scope creep; adds noise to unrelated code |
| Reformatting files with Black/isort | Changes hundreds of unrelated lines; makes diffs unreadable |
| Creating abstract base classes "for future flexibility" | Over-engineering; not in any bug's fix |
| Renaming variables for clarity | Not in scope; breaks grep-ability of known identifiers |
| Adding type annotations to old code | Not in any bug's fix scope |
| Running `git commit --amend` | Never modify git history; each fix is its own commit |

---

## HOW TO HANDLE UNEXPECTED SITUATIONS

**The file doesn't exist:**
→ Log as BLOCKED. Note the expected path. Do not create placeholder files.

**The method named in the bug doesn't match what you find:**
→ Read the file. Search for the behavior described. If you find it in a differently-named method, fix it there and log the discrepancy.

**The bug is already fixed (someone fixed it before this session):**
→ Quote the code that proves it's fixed. Log as SKIPPED with evidence.

**Your fix causes a test to fail that was already failing before:**
→ Continue — pre-existing failures are not your regression. Note it in the log.

**Your fix causes a test to fail that was passing before:**
→ Revert. Log as BLOCKED. The fix approach needs rethinking — do not force it.

**You find a new bug while fixing a known one:**
→ Do NOT fix it now. Add a new entry to FIX_LOG.md under a "New Bugs Discovered" section. Return to it only after completing all 33 known bugs.

**A dependency between two bugs:**
→ Fix the blocking bug first. The bug list is ordered to minimize this, but if you find a dependency not reflected in the order, note it and reorder locally.

---

*End of prompt. Begin with Phase 0. Do not write a single line of fix code until the CODEBASE_MAP.md is complete.*
