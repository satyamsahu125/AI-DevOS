# Commands

Everything needed to set up, run, and test AI DevOS. See `docs/CURRENT-STATE.md` for what these
pieces actually do.

## Prerequisites (once)

```bash
# Ollama (local LLM provider) -- must be running before the backend starts
ollama serve
ollama pull qwen2.5-coder:7b
```

Bedrock is the alternative provider (no local model needed) — switch to it later via the Settings
page or `POST /settings/llm`, no restart required.

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

uvicorn app.main:app --reload   # http://localhost:8000, auto-restarts on file changes
```

Health checks: `GET /health` (process alive), `GET /ready` (Ollama reachable + model loaded + DB
connected).

## Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api/* to :8000
```

## Tests

```bash
cd backend
python -m pytest tests/ -q                    # full suite
python -m pytest tests/test_safety_policy.py -q   # one file

cd frontend
npx tsc -b --noEmit             # typecheck only
npm run build                   # typecheck + production bundle
```

## Typechecking after a change

Always run both after touching backend or frontend code, before calling anything done:

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npx tsc -b --noEmit && npm run build
```

## Useful one-off API calls

```bash
# Create a project
curl -s -X POST http://localhost:8000/projects -H "Content-Type: application/json" \
  -d '{"name":"my-app","description":"A todo app where users can add and complete tasks."}'

# Run the full 12-stage pipeline (blocks until done or failed)
curl -s -X POST http://localhost:8000/workflow/start -H "Content-Type: application/json" \
  -d '{"project_id":"<id>","request":"<same description>"}'

# Run/retry exactly one stage
curl -s -X POST http://localhost:8000/workflow/stage -H "Content-Type: application/json" \
  -d '{"project_id":"<id>","stage":"architect","request":"<description>"}'

# Stop an in-flight build (takes effect at the next retry/stage checkpoint)
curl -s -X POST http://localhost:8000/workflow/<id>/stop

# Check status / real generated files / logs
curl -s http://localhost:8000/workflow/<id>
curl -s http://localhost:8000/projects/<id>/files
curl -s "http://localhost:8000/projects/<id>/logs?since_id=0"

# Download the generated project as a zip (includes RUN_INSTRUCTIONS.md)
curl -s -o project.zip http://localhost:8000/projects/<id>/download

# Switch LLM provider at runtime (persists to backend/.env)
curl -s -X POST http://localhost:8000/settings/llm -H "Content-Type: application/json" \
  -d '{"provider":"ollama","model":"qwen2.5-coder:7b"}'
```
