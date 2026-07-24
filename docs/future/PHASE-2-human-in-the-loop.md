# Phase 2 — Real Human-in-the-Loop

## Problem, today

The Reviewer (`app/review/reviewer.py`) tags findings `AUTO_FIX` / `ASK_HUMAN` / `FLAG`, and
`ASK_HUMAN` is the tier that blocks approval — but there is no actual human-in-the-loop mechanism
behind that name. When a stage exhausts `RetryPolicy.max_retries` (3), `WorkflowEngine.run()` just
returns `success=False` and the pipeline stops. The only recovery path is clicking "Retry stage,"
which re-runs the exact same prompt with the same context and no new information — if the model was
wrong the same way three times, a plain retry is likely to fail the same way a fourth time. This was
already observed and explained (not fixed) earlier in this project: "ask_human" is an internal
severity label, not a pause-and-wait mechanism.

## Why this matters

The whole point of a three-tier review system that distinguishes "ask a human" from "auto-fix" is
wasted if "ask a human" never actually surfaces a real, answerable question to a real human. Right
now the distinction between ASK_HUMAN and a hard failure is invisible to the user — both just show
up as "failed" in the UI.

## How to build it

1. **A real paused state**, distinct from `failed`. When retries exhaust on an `ASK_HUMAN` finding
   (not a plain content-empty AUTO_FIX case), persist the specific question(s)
   (`ReviewFinding.description`/`suggestion`) to `project.json` as `"paused_question"` instead of
   only `"failed_stage"`.
2. **A frontend answer surface.** In `ProjectPanel`, when `status.status === "awaiting_human"`, show
   the actual question(s) the reviewer raised and a text input for the answer — not just a generic
   "failed" badge and a blind retry button.
3. **Resume with the answer folded in.** `POST /workflow/stage` already accepts an override
   `request` string — reuse that: the answer gets appended to the retry content the same way
   `_build_retry_content()` already injects reviewer feedback, so the next attempt has genuinely new
   information instead of repeating the same prompt.
4. **Don't burn a retry on the wait.** The attempt counter should not have already been exhausted
   when the human answers — either reserve one "post-answer" attempt outside the normal 3, or reset
   the counter once real new information (the human's answer) is added to the prompt.

## Advantage

Turns "the AI team got stuck" from a dead end into an actual conversation — the system asks a
specific, answerable question instead of failing silently, and the human's answer measurably changes
what the next attempt tries, instead of just being a re-roll of the same dice.
