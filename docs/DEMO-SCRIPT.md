# AI DevOS — Demo Script
**Duration**: 3 minutes
**Goal**: Show a complete project generated from one prompt

## Before Recording
  1. Make sure Ollama is running:
     ```bash
     ollama serve
     ollama pull qwen2.5-coder:7b
     ```

  2. Start the backend:
     ```bash
     cd backend && uvicorn app.main:app --port 8000
     ```

  3. Start the frontend:
     ```bash
     cd frontend && npm run dev
     ```

  4. Open localhost:5173 in a clean browser window
     (incognito, no extensions visible)

  5. Have a second terminal ready to show
     `temp-workspace/` folder contents

## Demo Flow (3 minutes)

### 0:00-0:20 — Introduction
  Open AI DevOS homepage.
  Say: "AI DevOS turns a text description into a
         complete, runnable software project.
         Let me show you."

### 0:20-0:45 — Create Project
  Click "New Project" or type in the homepage input.
  Type: "Build a todo app where users can create,
         complete, and delete tasks"
  Click "Start Building"

### 0:45-1:30 — Q&A Stage
  Show Q&A panel appearing.
  Answer 3-4 questions quickly:
    "Who uses it?" → "Personal use"
    "Login required?" → "No auth needed"
    "Expected users?" → "Just me, under 100"
  Click "Start Building" / Continue.

### 1:30-2:00 — Pipeline Running
  Show pipeline progress view.
  Call out stages as they complete:
    "Strategic Review is assessing the project..."
    "Product Owner writing requirements..."
    "Architect designing the system..."
  Point out the live logs streaming in real time.
  Show the WebSocket connection dot (green).

### 2:00-2:30 — Files Being Generated
  Switch to Files & Code tab.
  Show files appearing one by one as Backend runs:
    backend/main.py
    backend/models/todo.py
    backend/routers/todos.py
  Click one file to show real Python code.
  Say: "Real files. Not a description of files."

### 2:30-2:50 — Complete Project
  Pipeline reaches Retrospective.
  Click "Download ZIP"
  Show the ZIP downloading.
  Open a terminal, unzip, show the file structure.
  Run: `cd todo-app && pip install -r requirements.txt && python backend/main.py`
  Show: "Running on http://localhost:8001"

### 2:50-3:00 — Metrics
  Switch to Metrics tab.
  Show: "24 LLM calls, 48,000 tokens, 0 cost (local Ollama)"
  Say: "Completely free. Runs on your own machine."

## After Recording
  Tag: `git tag v2.3-demo-ready`
