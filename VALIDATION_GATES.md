# AI DevOS — Validation Gates & Approval Semantics (VALIDATION_GATES.md)

## Objective

This document defines the formal verification gates required for pipeline stage qualification. Stage approval MUST NOT occur merely because file-writing operations completed without error.

---

## 1. Separation of Verification Tiers

The DevOS evaluates pipeline progress across 3 distinct tiers:

```
                  ┌──────────────────────────────┐
                  │      GENERATION SUCCESS      │
                  │   Files written, valid AST   │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │      VALIDATION SUCCESS      │
                  │  Lint=0, Build=OK, Test > 0  │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │        STAGE APPROVAL        │
                  │   Reviewer approved & gate   │
                  └───────────────────────────────┘
```

1. **GENERATION SUCCESS**: The agent executed and produced valid syntactical content (passing AST/syntax parser check).
2. **VALIDATION SUCCESS**: Code compiled/built successfully without lint errors (`lint_errors = 0`), and automated test suite executed with zero failing tests.
3. **STAGE APPROVAL**: Reviewer verified artifact quality and cross-stage consistency without `ASK_HUMAN` blockers.

---

## 2. Gate Criteria Matrix

| Verification Check | GENERATION SUCCESS | VALIDATION SUCCESS | STAGE APPROVAL |
| :--- | :--- | :--- | :--- |
| **AST / Syntax Check** | Required (`PASS`) | Required (`PASS`) | Required (`PASS`) |
| **Path Boundary Safety** | Required (`PASS`) | Required (`PASS`) | Required (`PASS`) |
| **Lint Errors** | Ignored | Must be `0` | Must be `0` |
| **Build Status** | Ignored | Must be `True` | Must be `True` |
| **Tests Discovered** | Ignored | Must be `> 0` for code stages | Must be `> 0` for code stages |
| **Tests Passed** | Ignored | `100%` of discovered | `100%` of discovered |
| **Reviewer Findings** | Ignored | No `AUTO_FIX` blockers | No `ASK_HUMAN` blockers |

---

## 3. Handling Unverified & Unsupported Environment Capabilities

If the current environment cannot execute a required validation check (e.g. Docker unavailable for sandbox execution or native build tools missing):

- The status MUST be marked as **`UNVERIFIED`** (not `APPROVED`).
- The pipeline report MUST log an unverified capability warning:

```json
{
  "stage": "FrontendDeveloper",
  "status": "UNVERIFIED",
  "reason": "Environment missing Node/Vite build toolchain to perform sandbox validation."
}
```

---
*Validation Gates Specification — AI DevOS Phase 10*
