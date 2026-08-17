@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM run-e2e-tests.bat — Run Playwright E2E tests for AI DevOS (Windows)
REM
REM Prerequisites:
REM   1. Both servers running (run dev.bat first)
REM   2. Node.js 18+ installed
REM
REM Usage:
REM   run-e2e-tests.bat          -- full suite
REM   run-e2e-tests.bat smoke    -- smoke tests only (fast, no LLM)
REM   run-e2e-tests.bat install  -- install Playwright first run
REM ─────────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "MODE=%~1"

echo [e2e] AI DevOS Playwright Test Runner
echo.

REM ── Step 1: Verify servers are running ───────────────────────────────────────
echo [e2e] Checking servers...
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health > %TEMP%\health.txt 2>nul
set /p HEALTH_CODE=<%TEMP%\health.txt
if "%HEALTH_CODE%"=="200" (
    echo [e2e] Backend: RUNNING (port 8000)
) else (
    echo [e2e] ERROR: Backend is not running on port 8000
    echo [e2e] Start it with: cd backend ^&^& venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
    exit /b 1
)

curl -s -o nul -w "%%{http_code}" http://localhost:5173 > %TEMP%\frontend.txt 2>nul
set /p FRONTEND_CODE=<%TEMP%\frontend.txt
if "%FRONTEND_CODE%"=="200" (
    echo [e2e] Frontend: RUNNING (port 5173)
) else (
    echo [e2e] WARNING: Frontend may not be running on port 5173
    echo [e2e] Start it with: cd frontend ^&^& npm run dev
)

echo.

REM ── Step 2: Install Playwright if requested ───────────────────────────────────
if "%MODE%"=="install" (
    echo [e2e] Installing Playwright...
    cd /d "%ROOT%e2e"
    npm install
    npx playwright install chromium
    echo [e2e] Playwright installed. Run again without 'install' to run tests.
    exit /b 0
)

REM ── Step 3: Run tests ─────────────────────────────────────────────────────────
cd /d "%ROOT%e2e"

if not exist "node_modules\@playwright\test" (
    echo [e2e] ERROR: Playwright not installed. Run: run-e2e-tests.bat install
    exit /b 1
)

if "%MODE%"=="smoke" (
    echo [e2e] Running smoke tests only...
    npx playwright test --config playwright.config.ts tests/07-ui-smoke.spec.ts --reporter=line
) else (
    echo [e2e] Running full test suite (this will take 30-60 minutes with LLM pipeline tests)...
    npx playwright test --config playwright.config.ts --reporter=html,line 2>&1 | tee test-run.log
)

echo.
echo [e2e] Tests complete. Open report with:
echo   cd e2e ^&^& npx playwright show-report report
