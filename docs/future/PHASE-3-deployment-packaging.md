# Phase 3 — Deployment & Packaging

## Problem, today

`DevOpsAgent` (stage 11 of 12) produces an advisory document — "deployment/ops guidance" — the same
way StrategicReview or Document do. It never writes a real file. So a user who downloads the
generated project (`GET /projects/{id}/download`) gets real backend/frontend source plus a
`RUN_INSTRUCTIONS.md`, but no `Dockerfile`, no `docker-compose.yml`, no CI config — despite having a
whole pipeline stage explicitly named after that job.

## Why this matters

This is the most visible gap between "the pipeline has a DevOps stage" and "the pipeline produces
DevOps output." Everything needed to make this real already exists: `WriteProjectFilesAction`
already knows how to turn a plan into real per-file writes with `ProjectFileManager`, and Phase 1's
verification step would give DevOps something concrete to react to (a known-working install/run
path) instead of guessing.

## How to build it

1. **Give DevOps a file plan too**, or extend the existing File Structure Planner to also plan a
   small number of infra files (`Dockerfile`, `docker-compose.yml`, `.dockerignore`,
   `.github/workflows/ci.yml`) tagged `responsible_stage: "devops"`.
2. **Reuse `WriteProjectFilesAction`** for DevOps the same way Backend/Frontend already do — one
   focused LLM call per infra file, written to `project/` (not nested under `backend`/`frontend`,
   since these describe the whole project) via `ProjectFileManager`.
3. **Feed it real signal**: the detected stack per area (already computed in
   `app/workspace/project_readme.py::summarize_area`) and the actual dependency manifest (Phase 1)
   are exactly what a real Dockerfile needs — no guessing what base image or install command to use.
4. **Include infra files in the download zip** alongside backend/frontend, and mention them in
   `RUN_INSTRUCTIONS.md`'s output (e.g. "or just run `docker compose up`").

## Advantage

The DevOps stage starts producing what its name promises. A downloaded project goes from "here's
the code, figure out how to containerize/deploy it yourself" to "here's the code and a working
Dockerfile/CI config generated from what was actually built" — closing the single biggest gap
between the pipeline's stage list and its actual file output.
