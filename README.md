# AI DevOS

> Transform a text description into a complete, runnable software project using a 12-stage AI engineering pipeline. Runs locally on Ollama — free.

## What It Does

AI DevOS takes one sentence like:
  "Build a todo app where users can create and delete tasks"

And produces:
  ✓ Product requirements with REQ-IDs and acceptance criteria
  ✓ System architecture with typed modules and API contracts
  ✓ Security review of the specific architecture
  ✓ Sprint plan breaking work into manageable phases
  ✓ Real backend Python files (FastAPI + SQLAlchemy)
  ✓ Real frontend files (React + Tailwind + shadcn/ui)
  ✓ Real pytest test files that run
  ✓ Dockerfile and docker-compose.yml
  ✓ README.md generated from actual code
  ✓ Downloadable .zip of the complete project

## How It's Different

| Feature | AI DevOS | gstack | MetaGPT | Devin |
|---------|----------|--------|---------|-------|
| Runs locally (free) | ✅ | ❌ | ❌ | ❌ |
| 12 specialized agents | ✅ | Slash commands | ✅ | ✅ |
| Real files on disk | ✅ | ✅ | Partial | ✅ |
| Agile sprints | ✅ | ❌ | ❌ | ❌ |
| User Q&A before coding | ✅ | ❌ | ❌ | ❌ |
| Requirement changes mid-project | ✅ | ❌ | ❌ | ❌ |
| Cross-project learning | ✅ | ❌ | ❌ | ❌ |
| Open source | ✅ | ✅ | ✅ | ❌ |
| Cost | Free | Claude API | OpenAI API | $500/mo |

## The 12-Stage Pipeline

Q&A → Strategic Review → Product Owner → Architect → Designer → Security → Sprint Planner → Scrum Master → File Planner → Backend Developer → Frontend Developer → QA → Documentation → DevOps → Retrospective

Each stage: LLM generates → Reviewer validates → Approved or retry with feedback → Next stage.

## Prerequisites

- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com) (local LLM — free)
- Git

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ai-devos.git
cd ai-devos

# 2. Start Ollama with recommended model
ollama serve
ollama pull qwen2.5-coder:7b

# 3. Install backend
cd backend
pip install -r requirements.txt
cp .env.example .env

# 4. Start backend
uvicorn app.main:app --port 8000 --reload

# 5. Install and start frontend (new terminal)
cd frontend
npm install
npm run dev

# 6. Open http://localhost:5173
```

## Recommended Models (Ollama)

| Role | Model | Why |
|------|-------|-----|
| Code generation | qwen2.5-coder:7b | Fast, good code quality |
| Architecture decisions | deepseek-r1:14b | Better reasoning |
| Requirements/Q&A | qwen3:8b | Conversational |

## Switching to AWS Bedrock

Settings → LLM Provider → Bedrock
Enter: AWS region, model ID, API key
Switches at runtime — no restart needed

## Running Tests

```bash
cd backend
python -m pytest tests/ -q
# 250+ tests, 0 failures
```

## Architecture

See [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) for the complete technical description.

## License

MIT — use it, modify it, ship it.
