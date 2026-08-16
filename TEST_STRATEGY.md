# AI DevOS — Automated Verification & Test Strategy (TEST_STRATEGY.md)

## Objective

The DevOS platform MUST verify software functionality through automated test execution, not merely through file-writing or build status checks.

---

## 1. Backend Test Generation Requirements

For every backend endpoint implemented, the QAAgent / BackendDeveloper MUST generate or locate unit and integration tests covering 12 mandatory criteria:

1. **Happy Path**: Successful invocation with valid input and `200/201` response.
2. **Invalid Input**: Malformed types or validation errors returning `422 Unprocessable Entity`.
3. **Missing Input**: Omitted required fields in body/query parameters.
4. **Boundary Values**: Min/max boundaries for numeric fields and string lengths.
5. **Authentication**: Missing Bearer token or invalid API key returning `401 Unauthorized`.
6. **Authorization**: Insufficient role permissions returning `403 Forbidden`.
7. **Not Found**: Request for non-existent resource ID returning `404 Not Found`.
8. **Duplicate Operations**: Idempotency check for duplicate creation returning `409 Conflict`.
9. **Malformed Payload**: Non-JSON body or corrupt payload returning `400 Bad Request`.
10. **Server Errors**: Unhandled internal exceptions returning formatted `500 Internal Server Error`.
11. **Response Schema**: Exact field match against Pydantic schema / OpenAPI contract.
12. **Status Codes**: Correct HTTP status codes on every execution branch.

---

## 2. Frontend Component & Integration Verification

For every frontend module:

- **Rendering**: Assert component mounts without crashing or emitting unhandled React errors.
- **Navigation**: Verify router transitions between screens.
- **User Interactions**: Click, input typing, and select dropdown events.
- **Form Validation**: Immediate inline error text on invalid input.
- **API Integration**: Mocked fetch / Axios response handling against `APIContractArtifact`.
- **States**: Verify rendering under 8 states (Default, Hover, Active, Disabled, Loading, Empty, Error, Success).

---

## 3. End-to-End (E2E) Critical Journey Verification

Example: Food Delivery E2E Path:
```
User Registration / Login
  └── Restaurant Discovery & Search
       └── Menu View & Item Selection
            └── Add to Cart & Modify Quantities
                 └── Checkout & Payment Processing
                      └── Order Creation & Order Status Tracking
```

---

## 4. Test Discovery & Coverage Gap Policy

1. **Test Discovery Phase**:
   - Inspect workspace for test runner configuration (`pytest.ini`, `vitest.config.ts`, `jest.config.js`).
   - Discover executable test files (`test_*.py`, `*.test.tsx`, `*.spec.ts`).

2. **TEST_COVERAGE_GAP Policy**:
   - IF zero tests are discovered for a code-writing stage (Backend / Frontend), the system MUST report `TEST_COVERAGE_GAP`.
   - `tests=0/0` MUST NOT be automatically treated as full stage approval.

---
*Test Strategy — AI DevOS Phase 11 & 12*
