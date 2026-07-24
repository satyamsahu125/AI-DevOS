# AI DevOS

A multi-agent software engineering pipeline: describe an application in plain English, and 12
specialized AI agents — each backed by an LLM call, a structured-output schema, and an automated
reviewer — carry it from idea to a real, downloaded, runnable codebase.

Unlike asking an LLM to write an app in one shot, every stage's output is validated against a
schema and passed through a three-tier reviewer before the next stage sees it, and only two stages
(Backend/Frontend Developer) ever write to the actual generated project — everything else produces
a reviewable document the next stage reads as context.

For the full architecture, the 12-stage pipeline, how modules connect, and how the memory system
works, see **[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)**. For the roadmap, see
**[docs/future/README.md](docs/future/README.md)**.

## Quick start

Prerequisites: Python 3.12+, Node 18+, and either [Ollama](https://ollama.com) (local, default) or
an AWS Bedrock API key (switchable at runtime from the Settings page).

```bash
# 1. Local LLM (skip if you're using Bedrock instead)
ollama serve
ollama pull qwen2.5-coder:7b

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows -- source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload  # http://localhost:8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Open `http://localhost:5173`, create a project, describe what you want built, and press Start
Build. The full command reference (tests, one-off API calls, provider switching) is in
**[docs/COMMANDS.md](docs/COMMANDS.md)**.

## What you get

- A live pipeline view of all 12 stages, with real build logs as they happen.
- Real generated source files (not just documents) for the backend and frontend, with an
  auto-generated `package.json`/`requirements.txt` built from the imports the generated code
  actually uses.
- A "How to Run" guide and a one-click zip download of the generated project.
- Stop/Resume — an interrupted build (crash, restart) resumes from the last completed stage instead
  of starting over.

## Repository layout

```
backend/    FastAPI app -- the 12-agent pipeline, memory subsystems, LLM providers
frontend/   Vite + React + TypeScript -- Dashboard, Projects, and the build workspace
docs/       Architecture (CURRENT-STATE.md), commands (COMMANDS.md), roadmap (future/)
```

## Tests

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npx tsc -b --noEmit && npm run build
```
