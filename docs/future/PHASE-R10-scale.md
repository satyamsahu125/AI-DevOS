# Phase R10 — Scale + Production Hardening

**Timeline:** Week 14–18  
**Depends on:** R8 (auth complete — needed for per-user isolation in horizontal scaling) + R1–R9 all passing  
**Problem:** SQLite cannot handle concurrent writes from multiple pipeline runs. Gate pause state is in-memory (lost on restart). Vector index is in-process (cannot scale horizontally). No distributed tracing.  
**Outcome:** PostgreSQL + Redis + Celery + OpenTelemetry. AI DevOS can run as a multi-instance deployment serving multiple teams concurrently.

---

## When to Start R10

Do NOT start R10 until:
1. You have at least 3 concurrent users or teams using the system
2. SQLite write contention is actually observed (check for "database is locked" in logs)
3. R1–R9 are all fully passing

Premature infrastructure scaling is a common mistake. SQLite + threading is adequate for a team of 5–10. Start R10 only when the problem exists.

---

## PostgreSQL Migration

### Schema design

Replace the current multiple SQLite databases with a single PostgreSQL schema:

```sql
-- Previously: memory.db, artifacts.db, costs.db, users.db, file_index.db, learning.db, lessons.db

-- Unified schema with proper FK constraints
CREATE TABLE users (...);                     -- from R8
CREATE TABLE projects (...);                  -- add owner_id FK
CREATE TABLE project_shares (...);            -- from R8
CREATE TABLE stage_outputs (...);             -- replaces memory.db key-value
CREATE TABLE artifacts (...);                 -- replaces artifacts.db
CREATE TABLE cost_events (...);               -- replaces costs.db
CREATE TABLE file_index (...);               -- replaces file_index.db
CREATE TABLE trajectories (...);             -- replaces learning.db
CREATE TABLE lessons (...);                  -- replaces lessons.db
CREATE TABLE templates (...);               -- replaces template_engine.db
CREATE TABLE refresh_tokens (...);           -- from R8 JWT
```

### Migration strategy

1. Add SQLAlchemy + Alembic to requirements.txt
2. Create `backend/app/db/` package with `models.py` (SQLAlchemy ORM models) and `migrations/`
3. Write `alembic init` migration scripts: one per SQLite table
4. Write `migrate_sqlite_to_postgres.py` script: reads all existing SQLite data, writes to PostgreSQL
5. Run migration on a test copy first, validate row counts match
6. Only then update all DAO classes to use PostgreSQL session instead of SQLite connections

### No SQLAlchemy rewrites before R10

All existing DAO code uses raw `sqlite3`. **Do not refactor existing DAOs to SQLAlchemy before R10.** The risk of introducing bugs in working code is not worth it. R10 is the right time to migrate — do it once, do it correctly, with Alembic from day one.

---

## Redis for Gate Pause State

**Current problem:** `ExecutionStateRegistry` (or equivalent) holds gate pause events in process memory. If the API process restarts while a human is reviewing an architecture gate, the gate state is lost and the pipeline cannot be resumed.

**Fix:** Replace in-memory gate state dict with Redis hash:

```python
class RedisGateStateRegistry:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def set_waiting(self, project_id: str, gate: str) -> None:
        self._redis.hset(f"gate:{project_id}", "gate", gate)
        self._redis.hset(f"gate:{project_id}", "status", "waiting")
        self._redis.expire(f"gate:{project_id}", 86400)  # 24h TTL

    def get_state(self, project_id: str) -> dict | None:
        data = self._redis.hgetall(f"gate:{project_id}")
        return data if data else None

    def clear(self, project_id: str) -> None:
        self._redis.delete(f"gate:{project_id}")
```

Redis is already in `docker-compose.yml` (from Phase 6). R10 just switches the gate registry implementation.

---

## Enable Celery by Default

**Current state:** Celery is installed and `dispatch_pipeline()` falls back to threading when Redis is unavailable. In R10, Redis is always available.

**R10 actions:**
1. Set `CELERY_BROKER_URL=redis://redis:6379/0` in `docker-compose.yml` as the default (not commented out)
2. Set `CELERY_RESULT_BACKEND=redis://redis:6379/1` 
3. Increase `docker-compose.yml` Celery worker replicas to 2: `deploy.replicas: 2`
4. Validate that 5 concurrent pipeline runs complete without errors

**Celery task configuration:**
```python
# tasks/pipeline_task.py — update task settings
@app.task(bind=True, max_retries=0, time_limit=3600, soft_time_limit=3300)
def run_pipeline(self, project_id: str, run_id: str) -> None:
    ...
```

---

## KnowledgeMemory (HNSW) — Multi-Instance Strategy

**Current:** HNSW vector index is in-process and file-backed (`knowledge_index.bin`). Two API instances would each have their own index — knowledge learned by instance A is not available to instance B.

**Options (choose one based on scale needed):**

### Option A: Shared filesystem mount (simple, adequate for 2–3 instances)
Mount the HNSW index file on a shared NFS/EFS volume. Add a file lock for write operations. Read operations can proceed concurrently.

### Option B: pgvector (proper solution for 4+ instances)
Add `pgvector` extension to PostgreSQL. Replace HNSW in-process with pgvector similarity search. `KnowledgeMemory.search()` becomes a PostgreSQL query: `SELECT * FROM knowledge_embeddings ORDER BY embedding <=> $1 LIMIT 5`.

**R10 recommendation:** Start with Option A. Migrate to Option B only if similarity search latency becomes a bottleneck.

---

## OpenTelemetry

**File:** `backend/app/observability/tracing.py`

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def configure_tracing(endpoint: str = "http://otel-collector:4317") -> None:
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
```

**Instrumentation points:**
- Every pipeline run: `with tracer.start_as_current_span("pipeline.run") as span: span.set_attribute("project_id", project_id)`
- Every stage: `with tracer.start_as_current_span(f"stage.{stage_name}")`
- Every LLM call: `with tracer.start_as_current_span("llm.generate") as span: span.set_attribute("model", model); span.set_attribute("tokens", tokens)`

**docker-compose.yml:** Add `otel-collector` service (or use the ADOT Collector image).

---

## Load Testing

Before declaring R10 complete, run a load test:

```bash
# 5 concurrent pipeline runs (using locust or k6)
locust --users 5 --spawn-rate 1 --run-time 30m --headless \
  -f tests/load/pipeline_load_test.py
```

**Success criteria:**
- All 5 pipelines complete without errors
- No "database is locked" errors in logs
- No memory leaks (RSS stable after 30 minutes)
- P95 pipeline completion time not more than 2× single-pipeline baseline

---

## Exit Criteria

- [ ] All data stored in PostgreSQL (no SQLite databases except test fixtures)
- [ ] Gate pause state survives API pod restart (verify: pause gate → kill API → restart → resume works)
- [ ] 5 concurrent pipelines complete without errors or data corruption
- [ ] OpenTelemetry traces visible in collector for every pipeline run
- [ ] HNSW index accessible from 2 API instances (shared mount or pgvector)
- [ ] Celery workers process pipeline tasks (verify via Celery flower dashboard or task logs)
- [ ] Load test passes (criteria above)
- [ ] All R1–R9 exit criteria still passing
