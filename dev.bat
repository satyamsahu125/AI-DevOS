@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM dev.bat — Full development watch mode (Windows)
REM
REM Starts three processes in separate windows:
REM   [BACKEND]  uvicorn --reload  (watches backend\app\)
REM   [FRONTEND] vite dev server   (HMR on http://localhost:5173)
REM   [TESTS]    vitest watch mode (re-runs on save)
REM
REM Usage:
REM   dev.bat             -- all three
REM   dev.bat --no-tests  -- backend + frontend only
REM ─────────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "NO_TESTS=0"

for %%A in (%*) do (
    if "%%A"=="--no-tests" set "NO_TESTS=1"
)

REM ── Load .env ─────────────────────────────────────────────────────────────
if exist "%ROOT%backend\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /v "^#" "%ROOT%backend\.env"`) do (
        set "%%A=%%B"
    )
)

echo [dev.bat] Starting AI DevOS in development mode...
echo.

REM ── Backend ───────────────────────────────────────────────────────────────
echo [dev.bat] Starting backend  ^>  http://localhost:8000
start "AI DevOS - BACKEND" cmd /k "cd /d %ROOT%backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app --log-level info"

REM Brief pause so backend starts binding
timeout /t 2 /nobreak >nul

REM ── Frontend ──────────────────────────────────────────────────────────────
echo [dev.bat] Starting frontend ^>  http://localhost:5173
start "AI DevOS - FRONTEND" cmd /k "cd /d %ROOT%frontend && npm run dev"

REM ── Tests (optional) ──────────────────────────────────────────────────────
if "%NO_TESTS%"=="0" (
    echo [dev.bat] Starting vitest watch
    start "AI DevOS - TESTS" cmd /k "cd /d %ROOT%frontend && npm run test:watch -- --reporter=verbose"
)

echo.
echo [dev.bat] All services launched in separate windows.
echo.
echo   Backend   http://localhost:8000
echo   Frontend  http://localhost:5173
if "%NO_TESTS%"=="0" echo   Tests     vitest watch ^(auto-reruns on save^)
echo.
echo Close the windows individually to stop each service.
