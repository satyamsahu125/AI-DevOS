# AI DevOS Codebase Documentation & Architectural Baseline

> **Notice**: This documentation directory (`documents/`) was produced via a complete, independent reverse-engineering audit of the AI DevOS codebase. It reflects the **actual source code implementation**, rather than high-level documentation claims, TODOs, or architectural assumptions.

---

## Overview

AI DevOS is an autonomous software engineering platform designed to take a high-level project requirement or prompt and orchestrate multi-agent software development workflows across requirements engineering, system architecture, UI/UX design, security analysis, sprint planning, file structure generation, code synthesis, containerized build/test validation, QA, bug analysis, deployment planning, and retrospectives.

---

## Documentation Structure

| Document | Description |
| --- | --- |
| [`PRD.md`](./PRD.md) | Reverse-engineered Product Requirements Document detailing product vision, personas, capabilities, user journeys, and feature implementation status (Implemented vs. Partial vs. Missing). |
| [`TECHNICAL_ARCHITECTURE.md`](./TECHNICAL_ARCHITECTURE.md) | Comprehensive system architecture overview, subsystem mapping, kernel/runtime architecture, dependency graph, and execution pipeline. |
| [`SYSTEM_FLOW.md`](./SYSTEM_FLOW.md) | End-to-end operational execution flows, sequence diagrams, request lifecycles, background execution, and event broadcasting. |
| [`WORKFLOW_STATE_MACHINE.md`](./WORKFLOW_STATE_MACHINE.md) | Complete workflow state definitions, stage runner mechanics, sprint execution, transition logic, reviewer loops, and state transition matrices. |
| [`MEMORY_AND_RAG.md`](./MEMORY_AND_RAG.md) | Intelligence & retrieval layer spec covering vector index (HNSW), SQLite stores, episodic/semantic/sprint-scoped memory, and prompt context injection. |
| [`API_SPECIFICATION.md`](./API_SPECIFICATION.md) | Exhaustive REST & WebSocket API reference reverse-engineered from FastAPI routes with request/response models and auth rules. |
| [`DATABASE_ARCHITECTURE.md`](./DATABASE_ARCHITECTURE.md) | Relational & persistent storage design documenting all SQLite databases, table schemas, Alembic migrations, and persistence rules. |
| [`FRONTEND_SPECIFICATION.md`](./FRONTEND_SPECIFICATION.md) | React + Vite frontend application structure, routing, UI components, state management, API integration, and parity with backend APIs. |
| [`SECURITY_AND_ACCESS.md`](./SECURITY_AND_ACCESS.md) | Security audit report covering authentication (JWT / API Key), request limits, rate limiting, container isolation, prompt safety, and known risks. |
| [`DEPLOYMENT_ARCHITECTURE.md`](./DEPLOYMENT_ARCHITECTURE.md) | Infrastructure, Docker Compose setup, Celery task queue, Redis broker, OpenTelemetry, Prometheus metrics, and environment configurations. |
| [`QA_AND_TESTING.md`](./QA_AND_TESTING.md) | Test suite breakdown, unit/integration/E2E test mapping, coverage analysis, test fixtures, and testing gaps. |
| [`FEATURE_TICKETS.md`](./FEATURE_TICKETS.md) | Prioritized engineering action tickets (P0-P3) derived from audit gaps, architectural defects, security issues, and missing tests. |
| [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) | Executive summary of audit findings, risk matrix, implementation statuses, dead code inventory, and prioritized engineering roadmap. |

---

## Core System Axioms Discovered in Source Code

1. **Source Code is Truth**: If a feature is documented in `docs/` or claimed in a comment but missing in code (e.g. absent handler or stubbed response), it is classified as **Unimplemented** or **Stub**.
2. **Dual-Mode Execution**: Workflow stages can execute synchronously via FastAPI background tasks or asynchronously via **Celery + Redis**. If Celery/Redis is down, the system falls back gracefully to in-process background execution.
3. **Multi-Database Architecture**: AI DevOS maintains separate SQLite databases for explicit concerns (`auth.db`, `memory.sqlite`, `lessons.sqlite`, `learning.sqlite`, `knowledge.sqlite`, `file_index.db`, `costs.db`) rather than a single monolithic database.
4. **HNSW Vector Storage**: Semantic knowledge retrieval relies on `hnswlib` combined with `sentence-transformers` for embedding generation and local vector search.
5. **Phase-Based Evolution**: Code comments and test suites reflect a phased hardening evolution (Phase 1-6), culminating in structured logging, OTEL tracing, Alembic migrations, and rate/size middleware.
