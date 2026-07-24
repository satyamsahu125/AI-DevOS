# Phase 1 — Verified Output

## Problem, today

QA approval is currently a document review, not a real test: `QAAgent` writes a test plan/bug list
as a reviewable artifact, but nothing ever actually installs the generated project's dependencies,
imports its files, or runs anything. A file full of syntax errors can sail through the entire
pipeline as "complete" as long as the reviewer's schema/coverage checks pass. Separately, the
auto-generated `package.json`/`requirements.txt` (added this session) lists package names with no
version pins (`"*"` for npm, unpinned for pip) — a real `npm install` today could pull a different
major version tomorrow and break silently.

## Why this matters

Everything downstream (Deployment/Packaging in Phase 3, Analytics in Phase 4) is only as
trustworthy as the assumption that "complete" means "actually works." Right now that assumption is
unverified. This is the highest-leverage phase because it doesn't require new agents or schemas —
it makes the existing ones honest.

## How to build it

1. **Real dependency versions.** Resolve each detected package name (`app/workspace/dependency_detector.py`)
   against the npm registry / PyPI at generation time (or against a small curated known-good-version
   table to avoid a network dependency) and pin an actual version instead of `"*"`.
2. **A verification step after Backend/Frontend, before QA.** A new lightweight action —
   not a new LLM-backed agent, just a deterministic step in the pipeline — that:
   - runs `npm install --dry-run` (or an actual install into a throwaway dir) / `pip install --dry-run`
     against the generated manifest,
   - attempts to parse every generated file with the language's own parser (`node --check`,
     `python -m py_compile`) to catch syntax errors before QA ever sees the code,
   - records failures as `SafetyPolicy`-style structured results, feeding them into the Reviewer as
     real `ASK_HUMAN` findings instead of letting QA rubber-stamp broken code.
3. **Surface the verification result** in the frontend's Chat/Live Output, and in the downloaded
   zip's `RUN_INSTRUCTIONS.md` ("last verified: install succeeded / failed, syntax check passed/failed").

## Advantage

"Complete" starts meaning something concrete: the generated project's dependencies actually resolve
and its files actually parse, not just that an LLM's document review liked the shape of the output.
This is the difference between a demo and something a user can trust enough to actually run.
