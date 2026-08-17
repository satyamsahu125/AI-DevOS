# AI DevOS — E2E Test Report

**Suite version**: 1.0.0  
**Report generated**: 2026-08-17  
**Test framework**: Playwright 1.47.x  
**Environment**: AI DevOS at `F:\AI-DevOS3`  
**Backend**: FastAPI + uvicorn on `http://localhost:8000`  
**Frontend**: Vite/React on `http://localhost:5173`  
**LLM provider**: AWS Bedrock (`qwen.qwen3-next-80b-a3b`)  
**Auth**: `AUTH_ENABLED=false` (anonymous admin, no tokens required)  
**Human gates**: `REQUIRE_HUMAN_APPROVAL=false` (pipeline runs end-to-end)  
**Sandbox**: `SANDBOX_ENABLED=false` in `backend/.env`  

---

## Execution Status

> **Tests have NOT been executed automatically.**
>
> Execution was blocked by two infrastructure constraints in the cloud build environment:
>
> 1. **npm registry policy** — `npm install @playwright/test` returned HTTP 403 Forbidden on
>    the device's npm registry. Playwright cannot be installed without a registry exception or
>    a local package cache.
>
> 2. **Windows binaries cannot run in the Linux device-VM** — `uvicorn.exe` and other Windows
>    executables exit with `Exec format error` when invoked from the Linux shell that
>    backs the device bridge. The backend server cannot be started from automation.
>
> **All test infrastructure is fully written and on disk.** To run the suite, follow the
> manual steps in the [How to Run](#how-to-run) section below.

---

## Infrastructure Written

| File | Location | Description |
|------|----------|-------------|
| `playwright.config.ts` | `e2e/` | Playwright configuration — workers=1, serial, Chromium, webServer entries |
| `helpers/api.ts` | `e2e/helpers/` | HTTP helper functions aligned to actual API contract |
| `pages/ProjectPage.ts` | `e2e/pages/` | Page Object for `/projects/:id` workspace UI |
| `tests/01-project-creation.spec.ts` | `e2e/tests/` | B-01, B-02, B-05 |
| `tests/02-pipeline-flow.spec.ts` | `e2e/tests/` | B-29, B-20, B-19 |
| `tests/03-context-injection.spec.ts` | `e2e/tests/` | B-06, B-07, B-08, B-11 |
| `tests/04-sandbox-qa.spec.ts` | `e2e/tests/` | B-15, B-31, B-17, B-16 |
| `tests/05-memory-api.spec.ts` | `e2e/tests/` | B-09, B-10, B-21, B-22, B-28 |
| `tests/06-qa-prompts.spec.ts` | `e2e/tests/` | B-24, B-25, B-32, B-33, B-26 |
| `tests/07-ui-smoke.spec.ts` | `e2e/tests/` | Health, API contract, B-15 code, B-22, B-25/B-10 |
| `package.json` | `e2e/` | npm scripts (`test`, `test:smoke`, per-file scripts) |
| `tsconfig.json` | `e2e/` | TypeScript compiler config |
| `run-e2e-tests.bat` | project root | Windows batch runner with server health checks |
| `DISCOVERY_NOTES.md` | project root | Full API contract discovery log |

---

## Bug Coverage Matrix

Legend: `PENDING` = infrastructure ready, awaiting manual run | `SKIPPED` = excluded per spec | `CODE-ONLY` = fix confirmed by code inspection (no runtime needed)

| Bug ID | Description | Test File | Test Name | Status |
|--------|-------------|-----------|-----------|--------|
| B-01 | React Native scaffold goes in `app/` not `backend/` | `01-project-creation.spec.ts` | `[B-01][B-02] React Native project generates files in app/...` | PENDING |
| B-02 | Python project scaffold goes in `backend/` not root | `01-project-creation.spec.ts` | `[B-01] Python FastAPI project generates files in backend/` | PENDING |
| B-03 | *(already confirmed fixed — test not needed)* | — | — | SKIPPED |
| B-04 | *(already confirmed fixed — test not needed)* | — | — | SKIPPED |
| B-05 | React Native missing `App.tsx`, `babel.config.js`, `tsconfig.json` | `01-project-creation.spec.ts` | `[B-05] React Native project has scaffold files` | PENDING |
| B-06 | BackendDeveloper does not receive architect artifact in context | `03-context-injection.spec.ts` | `[B-06] BackendDeveloper generates files referencing the architect spec` | PENDING |
| B-07 | FrontendDeveloper generates generic/domain-irrelevant content | `03-context-injection.spec.ts` | `[B-07] FrontendDeveloper generates files with domain-relevant content` | PENDING |
| B-08 | FrontendDeveloper does not receive backend API contracts | `03-context-injection.spec.ts` | `[B-08] FrontendDeveloper receives backend API contracts in context` | PENDING |
| B-09 | Stage messages stored under wrong key in memory | `05-memory-api.spec.ts` | `[B-09] Stage messages stored under stage-specific keys` | PENDING |
| B-10 | Architect output truncated to 1000 chars before storage | `05-memory-api.spec.ts` | `[B-10] Architect output is not truncated to 1000 chars` | PENDING |
| B-11 | BugAnalyst context missing sandbox results | `03-context-injection.spec.ts` | `[B-11] BugAnalyst context includes sandbox results key` | PENDING |
| B-15 | `SANDBOX_ENABLED` default not changed to `true` in code | `04-sandbox-qa.spec.ts` + `07-ui-smoke.spec.ts` | `[B-15]` code check + `/ready` smoke | PENDING |
| B-16 | Post-QA sandbox run not scheduled | `04-sandbox-qa.spec.ts` | `[B-16] Post-QA sandbox run is scheduled` | PENDING |
| B-17 | Mobile QA uses calculator-specific templates | `04-sandbox-qa.spec.ts` | `[B-17] Mobile project QA does not use calculator-specific test templates` | PENDING |
| B-19 | ChangeManager injection not wired — BugAnalyst rollback silent | `02-pipeline-flow.spec.ts` | `[B-19] ChangeManager injection is wired` | PENDING |
| B-20 | After replanning, release stages not cleared from stages_completed | `02-pipeline-flow.spec.ts` | `[B-20] After replanning, release stages are cleared` | PENDING |
| B-21 | Context assembler exceeds per-stage token budget | `05-memory-api.spec.ts` | `[B-21] Context assembler does not exceed per-stage token budget` | PENDING |
| B-22 | Knowledge memory store: concurrent writes not atomic | `05-memory-api.spec.ts` + `07-ui-smoke.spec.ts` | `[B-22]` concurrent writes + stats endpoint | PENDING |
| B-24 | Architecture sizing rules only cover web-tier | `06-qa-prompts.spec.ts` | `[B-24] Architecture sizing rules cover mobile patterns` | PENDING |
| B-25 | Architect artifact truncated to 2000 chars to BackendDeveloper | `06-qa-prompts.spec.ts` + `07-ui-smoke.spec.ts` | `[B-25]` deep-spec terms + config check | PENDING |
| B-26 | `_inject_template()` type annotation wrong (tuple arity) | `06-qa-prompts.spec.ts` | `[B-26] context_assembler.py compiles without type annotation error` | CODE-ONLY† |
| B-27 | *(already confirmed fixed — test not needed)* | — | — | SKIPPED |
| B-28 | TechLead artifact endpoint missing after sprint | `05-memory-api.spec.ts` | `[B-28] TechLead artifact endpoint exists after sprint` | PENDING |
| B-29 | False-alarm context-window overflow after multiple stages | `02-pipeline-flow.spec.ts` | `[B-29] Pipeline does not false-alarm context-window overflow` | PENDING |
| B-30 | *(already confirmed fixed — test not needed)* | — | — | SKIPPED |
| B-31 | Sprint QA step missing from pipeline | `04-sandbox-qa.spec.ts` | `[B-31] Sprint QA step appears in the pipeline` | PENDING |
| B-32 | `_build_mobile_prompt()` concatenates system + user prompt | `06-qa-prompts.spec.ts` | `[B-32] QA mobile prompt structure` | PENDING |
| B-33 | `_WEB_SYSTEM_PROMPT` hardcodes FastAPI import + auth endpoint | `06-qa-prompts.spec.ts` | `[B-33] Web QA prompt does not hardcode FastAPI import path` | PENDING |

† B-26 is verified at server startup: if `context_assembler.py` failed to import due to the wrong annotation, the backend process would not start and `/health` would return non-200. The smoke test `[B-26]` asserts `GET /health` returns 200 as a proxy for successful import.

**Totals**: 23 PENDING | 4 SKIPPED (B-03, B-04, B-27, B-30) | 0 PASS | 0 FAIL

---

## Critical Discovery: API Contract Corrections

The test spec assumed a `project_type` field on `ProjectRequest`. This field **does not exist**.

| Assumed (wrong) | Actual |
|-----------------|--------|
| `POST /api/projects` | `POST /api/v1/projects/create-and-run` |
| `{ name, description, project_type }` | `{ name, description, mode }` |
| `GET /api/projects/{id}/status` | `GET /api/v1/projects/{id}` |
| `project_type: 'react_native'` | Project type inferred from `description` text by LLM |

All test files and helpers were written against the **actual** API contract discovered by reading source files. Project type is signaled to the LLM via natural language in the `description` field (e.g., "A React Native mobile app…").

---

## Pre-existing Test Failures (Expected)

These unit tests were known-failing before this E2E suite was written. They are separate from the Playwright suite and do not affect E2E results.

| Unit test | File | Reason |
|-----------|------|--------|
| `test_sandbox_enabled_default_is_false` | Backend unit tests | B-15 changed the code default to `true`; this old test expected `false` and was not updated in the fix |
| `test_predecessor_truncated` | Backend unit tests | B-10 changed truncation from 1000→6000 chars; the old test asserted the truncated value |

---

## Coverage Gaps

| Gap | Reason |
|-----|--------|
| `/api/v1/prompts/preview` endpoint | Does not exist in router.py. Tests B-32 and B-33 fall back to pipeline-level verification when the endpoint is absent. |
| `/api/v1/config/context-budget` endpoint | Does not exist. B-25/B-10 check is advisory in the smoke test. |
| `/api/v1/debug/modules/{module}` endpoint | Does not exist. B-26 falls back to `/health` liveness check. |
| B-19 ChangeManager rollback | Requires a specific pipeline failure mid-stream — hard to trigger deterministically without LLM cooperation. Test uses status-field heuristic. |
| B-20 Replanning trigger | Requires human-revise gate action while `REQUIRE_HUMAN_APPROVAL=true`. Test documents this dependency. |
| B-22 concurrent write | Race condition test simulates concurrent requests; actual atomicity depends on file-system locking in the running app. |

---

## How to Run

### Prerequisites

Both servers must be running before you start tests.

**Step 1 — Start both servers** (run from `F:\AI-DevOS3`):

```bat
dev.bat
```

Or manually in two separate terminals:

```bat
REM Terminal 1 — Backend
cd backend
venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app

REM Terminal 2 — Frontend
cd frontend
npm run dev
```

Wait until both are ready:
- Backend: `http://localhost:8000/health` → `{"status":"healthy"}`
- Frontend: `http://localhost:5173` → loads in browser

**Step 2 — Install Playwright** (first run only):

```bat
run-e2e-tests.bat install
```

This runs `npm install` and `npx playwright install chromium` inside the `e2e/` directory.

**Step 3 — Run the full suite**:

```bat
run-e2e-tests.bat
```

Or run only the fast smoke tests (no LLM calls, ~2 minutes):

```bat
run-e2e-tests.bat smoke
```

**Step 4 — View the HTML report**:

```bat
cd e2e
npx playwright show-report report
```

### Run individual test files

From `F:\AI-DevOS3\e2e`:

```bat
npx playwright test --config playwright.config.ts tests/07-ui-smoke.spec.ts --reporter=line
npx playwright test --config playwright.config.ts tests/01-project-creation.spec.ts --reporter=line
npx playwright test --config playwright.config.ts tests/05-memory-api.spec.ts --reporter=line
```

### Run order for fastest feedback

Run files in this order — later files depend on LLM pipeline which is slowest:

1. `07-ui-smoke.spec.ts` — ~2 min, no LLM, shows server health and API contract
2. `05-memory-api.spec.ts` — ~10 min, light LLM usage, fast API checks
3. `01-project-creation.spec.ts` — ~20 min, one LLM project per test
4. `03-context-injection.spec.ts` — ~30 min, context and artifact assertions
5. `04-sandbox-qa.spec.ts` — ~30 min, QA stage required
6. `06-qa-prompts.spec.ts` — ~30 min, includes architect artifact assertions
7. `02-pipeline-flow.spec.ts` — ~40 min, needs multi-stage completion

---

## Architecture Notes

### Workers = 1 (Serial)

The Playwright config sets `workers: 1` and `fullyParallel: false`. This is intentional:
- The AWS Bedrock LLM endpoint has concurrency limits.
- Concurrent projects running the same pipeline stages cause race conditions in context assembly.
- Serial execution with `test.setTimeout(300_000)` (5 min) per test provides stable results.

### Test Independence

Every test that creates a project:
1. Calls `createProject()` at the start to create a fresh, uniquely-named project.
2. Wraps all assertions in a `try/finally` block.
3. Calls `deleteProject()` in the `finally` block, even if the test fails.

This ensures no orphaned projects accumulate in the system across test runs.

### LLM Pipeline Tests

Tests that require the LLM pipeline to run a specific stage use `waitForStage(request, projectId, stage, timeoutMs)`. This polls `GET /api/v1/projects/{id}` every 5 seconds checking `stages_completed` and `current_stage`. Timeouts are generous (120–240 seconds per stage) to account for cold Bedrock latency.

### No Auth Required

`AUTH_ENABLED=false` in `backend/.env`. All API calls are made without Authorization headers. The middleware returns an anonymous admin user for all requests.

---

## File Tree

```
F:\AI-DevOS3\
├── DISCOVERY_NOTES.md          ← API contract discovery (read this first)
├── run-e2e-tests.bat           ← Windows test runner
└── e2e\
    ├── package.json            ← npm scripts
    ├── tsconfig.json           ← TypeScript config
    ├── playwright.config.ts    ← Playwright configuration
    ├── helpers\
    │   └── api.ts              ← HTTP helper functions (actual API contract)
    ├── pages\
    │   └── ProjectPage.ts      ← Page Object for /projects/:id
    └── tests\
        ├── 01-project-creation.spec.ts   B-01, B-02, B-05
        ├── 02-pipeline-flow.spec.ts      B-29, B-20, B-19
        ├── 03-context-injection.spec.ts  B-06, B-07, B-08, B-11
        ├── 04-sandbox-qa.spec.ts         B-15, B-31, B-17, B-16
        ├── 05-memory-api.spec.ts         B-09, B-10, B-21, B-22, B-28
        ├── 06-qa-prompts.spec.ts         B-24, B-25, B-32, B-33, B-26
        └── 07-ui-smoke.spec.ts           Health, API contract, B-15/B-22/B-25
```

---

*Report template ready — update PASS/FAIL columns after running `run-e2e-tests.bat`.*
