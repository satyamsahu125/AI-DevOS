# Safety & Execution Policy

**Status:** Canonical. Adopted from gstack's `careful`/`freeze`/`guard` patterns (research
§C3) and `investigate` pattern (research §C2/§C6-adjacent), mapped onto AI DevOS's
`ExecutionEngine`, which today has **zero guardrails and a no-op rollback mechanism**
(confirmed in PROMPT 2's codebase audit — `ExecutionRecovery.resume`/`rollback` unconditionally
return `success=True` regardless of whether anything was actually restored).

---

## SafetyPolicy

**What it guards:** any generated command, migration, or infrastructure-apply instruction
produced by an agent (primarily `BackendDeveloperAgent`, `DevOpsAgent`) before the
`ExecutionEngine` applies it.

**Check logic (gstack `/careful`-derived):** pattern-match the generated instruction against a
fixed list of destructive-operation signatures, checked against the **whole** instruction
string (not just the first token, to prevent a chained/obfuscated command from slipping
through a naive prefix check):

| Pattern | Risk |
|---|---|
| Recursive delete (`rm -r`/`-rf`, `--recursive`) | Irreversible data loss |
| `DROP TABLE` / `DROP DATABASE` / `TRUNCATE` | SQL data loss |
| `git push --force` / `-f` | History rewrite |
| `git reset --hard` | Uncommitted work loss |
| `git checkout .` / `git restore .` | Uncommitted work loss |
| `kubectl delete` | Production impact |
| `docker rm -f` / `docker system prune` | Container/image loss |

A safe-exception allowlist is checked **first** for known-benign cases (e.g. `rm -rf
node_modules|dist|__pycache__|.cache|build`), matched against the whole string, mirroring
gstack's specific defense against a benign-looking prefix hiding a dangerous suffix.

**Action on match:** unlike gstack's soft `ask` warning, AI DevOS's `ExecutionEngine` has no
human in the loop mid-stage — a match therefore causes the artifact to be routed to the
**Reviewer** with an explicit `safety_flag` attached, rather than applied directly. The
Reviewer's existing ASK-tier path (see `Reviewer` upgrade, PROMPT 3 §D1) is the correct place
for a human decision, not a new separate approval mechanism.

**Every match is logged** (pattern name only, never the full command content, to avoid
persisting sensitive data in logs) to `ObservabilityMemory`.

## FreezePolicy

**What it guards:** the set of file paths a given stage's agent is permitted to write to.

**Check logic (gstack `/freeze`-derived):** each stage declares its allowed write scope (e.g.
`BackendDeveloperAgent` may only write under `backend/`, `FrontendDeveloperAgent` only under
`frontend/`). Before the `ExecutionEngine` persists a `FileChange` from a `BackendCode`/
`FrontendCode` artifact, resolve the target path to an absolute path (resolving symlinks and
`..` segments) and string-prefix-check it against the stage's declared scope, with trailing-
slash normalization so `frontend` cannot match `frontend-legacy`.

**Action on violation:** **hard deny** — the specific `FileChange` is rejected and the artifact
is returned to the agent's stage for retry with an explicit reason, not silently dropped.
Gstack's own documentation is explicit that this is **not a security boundary** (a generated
shell command could still write outside the scope via `sed`/similar) — `SafetyPolicy` above is
what covers arbitrary commands; `FreezePolicy` only covers direct file-write artifacts.

**Relationship to rollback:** this is what makes AI DevOS's currently-fake rollback mechanism
meaningful — if writes are never allowed outside a stage's declared scope in the first place,
there is a bounded, known set of paths to actually roll back, instead of nothing to reason
about (as is the case today).

## InvestigationProtocol

**Iron Law (gstack `/investigate`-derived): no fix without root-cause investigation first.**
This governs the `Investigate`/retry-escalation path referenced in PROMPT 3's proposed
Investigate/Debug stage insertion point (between QA and any retry loop).

1. **Trace data flow.** Read the actual code path involved before forming any theory.
2. **Form one hypothesis.** Exactly one, stated explicitly — not a list of possibilities to
   try in parallel.
3. **Test the hypothesis.** Deterministically reproduce the failure to confirm or refute it.
4. **If wrong, form the next hypothesis.** Return to step 2, informed by what step 3 ruled out.
5. **After 3 failed hypotheses, escalate to human.** Do not continue guessing indefinitely.

**Never:** apply a fix without having first stated and tested a hypothesis for *why* the
failure occurred. A recurring failure in the same area across multiple runs is flagged (via
`LessonStore`) as an architectural smell, not just a bug — this is what feeds the
`Retrospective` stage's `what_failed` field.

**Integration point:** this protocol governs what happens when `WorkflowEngine`'s (currently
unused — PROMPT 2 finding) `RetryPolicy` triggers a retry. Retry attempt 1-3 each correspond to
one hypothesis-test cycle above; exceeding the retry limit is exactly "escalate to human" —
i.e., `RetryPolicy`'s existing max-retry concept and this protocol's step 5 are the same event,
not two separate mechanisms.
