@echo off
echo === AI DevOS Startup ===

:: Load .env if it exists
if exist backend\.env (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /v "^#" backend\.env`) do (
        set "%%A=%%B"
    )
)

if not defined LLM_MODEL set LLM_MODEL=qwen2.5-coder:7b

:: Check Ollama
echo [1/3] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not running.
    echo Start it with: ollama serve
    echo Pull model with: ollama pull %LLM_MODEL%
    pause
    exit /b 1
)
echo   Ollama OK

:: Install dependencies
echo [2/3] Installing dependencies...
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)
echo   Dependencies OK

:: Start server
echo [3/3] Starting AI DevOS API...
echo.
echo   API:  http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo   Frontend should run separately (cd frontend ^&^& npm run dev)
echo.
cd backend
:: --reload-dir app: watch ONLY the source code folder, not temp-workspace/
:: This prevents test file writes from triggering a server reload mid-pytest.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
