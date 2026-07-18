# Project Overview

## What this project does

This repository implements a lightweight backend service for creating and managing project workspaces, then running a simple workflow pipeline around them. The code is organized as a FastAPI application under the backend package and is primarily designed as a prototype orchestration layer rather than a production-grade AI coding platform.

## What I observed from the code

### 1. Main application entry point

The FastAPI app is created in [backend/app/main.py](../backend/app/main.py). It:

- starts an application lifecycle via a kernel object,
- includes the API router,
- registers a custom exception handler.

### 2. API surface

The API routes are defined in [backend/app/api/router.py](../backend/app/api/router.py) and include:

- health endpoints under /health and /ready,
- project endpoints under /projects,
- workflow endpoints under /workflow/start and /workflow/{project_id}.

The key API modules are:

- [backend/app/api/health.py](../backend/app/api/health.py)
- [backend/app/api/project.py](../backend/app/api/project.py)
- [backend/app/api/workflow.py](../backend/app/api/workflow.py)

### 3. Core domain flow

The application follows a simple flow:

1. Create a project through the project manager.
2. Create a workspace and initialize memory for that project.
3. Start a workflow stage.
4. Run an execution pipeline that creates an artifact.
5. Review the artifact and return workflow status.

The main pieces are:

- [backend/app/project/manager.py](../backend/app/project/manager.py) for creating projects
- [backend/app/workspace/manager.py](../backend/app/workspace/manager.py) for creating workspace folders
- [backend/app/memory/manager.py](../backend/app/memory/manager.py) for simple project memory storage
- [backend/app/workflow/engine.py](../backend/app/workflow/engine.py) for orchestrating the stage flow
- [backend/app/execution/pipeline.py](../backend/app/execution/pipeline.py) for generating artifacts
- [backend/app/review/manager.py](../backend/app/review/manager.py) for approving or rejecting the generated artifact

### 4. Current implementation maturity

From the code, this project appears to be an early-stage framework/prototype:

- It uses simple in-memory or file-based persistence.
- The LLM integration layer is minimal and not fully wired to a real model provider.
- The workflow and execution modules are present but lightweight.
- The tests focus on project creation and basic API smoke behavior.

### 5. Important modules

- [backend/app/llm/manager.py](../backend/app/llm/manager.py): very small stub for LLM-oriented operations.
- [backend/app/kernel/kernel.py](../backend/app/kernel/kernel.py): startup and shutdown orchestration.
- [backend/app/kernel/container.py](../backend/app/kernel/container.py): dependency wiring for the app.
- [backend/app/config/loader.py](../backend/app/config/loader.py): loads YAML config.
- [backend/app/shared](../backend/app/shared): shared DTOs, enums, and models used across the system.

## How to run it manually

### Prerequisites

- Python 3.10+
- Internet access if you want to install packages from pip

### 1. Create and activate a virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the API

From the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4. Check if it is running

In another terminal:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "healthy"}
```

### 5. Create a sample project

```powershell
curl -X POST http://127.0.0.1:8000/projects -H "Content-Type: application/json" -d "{\"name\":\"Demo Project\",\"description\":\"Sample\"}"
```

### 6. Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py"
```

## Ollama setup and manual use

The repository does not currently contain a full Ollama integration path in the main runtime. The LLM layer is still a stub in [backend/app/llm/manager.py](../backend/app/llm/manager.py). If you want to use Ollama as a local agent runtime, the practical setup is:

### 1. Install Ollama

Follow the official Ollama install steps for your platform.

### 2. Pull a model

Example:

```powershell
ollama pull qwen2.5-coder:7b
```

### 3. Verify it is available

```powershell
ollama list
```

Expected output includes the model, for example:

```text
NAME                ID              SIZE      MODIFIED
qwen2.5-coder:7b    dae161e27b0e    4.7 GB    5 days ago
```

### 4. Use it as a local agent backend

To make this repository use Ollama, you would need to replace or extend the current LLM stub with an implementation that:

- calls the Ollama API,
- sends prompts to the selected model,
- returns the model output to the existing workflow/execution pipeline.

At the moment, the project does not automatically use Ollama; it only exposes the scaffolding for an LLM manager.

## How to judge whether the project is working

A basic health check is:

- the API starts without errors,
- /health returns 200 with the expected payload,
- creating a project succeeds,
- tests pass.

The current repository already supports these checks.

## Summary

This project is a small, extensible orchestration prototype for:

- creating project workspaces,
- initializing project-specific memory,
- starting a workflow,
- generating simple artifacts,
- exposing the flow through a FastAPI API.

It is not yet a fully integrated LLM-native coding agent system, but it has the structure to grow into one.
