#!/usr/bin/env python3
"""
run_and_test.py  —  Start AI DevOS backend, create a project, watch it run.

Usage (from F:\AI-DevOS3):
    python run_and_test.py

What it does:
  1. Starts uvicorn in a background process
  2. Waits until the API is healthy
  3. Creates a new project via POST /projects/create-and-run
  4. Polls /workflow/{id}/status every 10 s
  5. Prints a live status table until qa_pending (or failure)
  6. Fetches and displays the generated clarification questions
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
BASE_URL     = "http://localhost:8000"
STARTUP_WAIT = 60    # max seconds to wait for uvicorn to be ready
POLL_TIMEOUT = 600   # max seconds to wait for qa_pending
POLL_INTERVAL = 10   # seconds between status polls

PROJECT_NAME = "Live Test: Todo App"
PROJECT_DESC = "Build a simple todo list web app where users can add, complete, and delete tasks"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def p(color, msg): print(f"{color}{msg}{RESET}")
def ok(msg):   p(GREEN,  f"  ✓ {msg}")
def fail(msg): p(RED,    f"  ✗ {msg}")
def info(msg): p(CYAN,   f"  → {msg}")
def warn(msg): p(YELLOW, f"  ! {msg}")

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(path, timeout=60):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def post(path, body, timeout=60):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# ── Step 1: Start uvicorn ─────────────────────────────────────────────────────

def start_backend():
    p(BOLD, "\n[1/4] Starting backend (uvicorn)...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload-exclude", "temp-workspace",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Stream output until "Application startup complete"
    ready = False
    deadline = time.time() + STARTUP_WAIT
    print("    (streaming uvicorn output...)")
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.rstrip()
        print(f"    {line}")
        if "Application startup complete" in line or "Uvicorn running" in line:
            ready = True
            break
        if proc.poll() is not None:
            fail(f"uvicorn exited early (code {proc.returncode})")
            sys.exit(1)

    if not ready:
        # Try health check anyway — maybe it started but output was different
        try:
            d = get("/health", timeout=5)
            if d.get("status") in ("ok", "healthy"):
                ready = True
        except Exception:
            pass

    if not ready:
        fail("Backend did not start in time.")
        proc.terminate()
        sys.exit(1)

    ok("Backend started")
    return proc

# ── Step 2: Health check ──────────────────────────────────────────────────────

def check_health():
    p(BOLD, "\n[2/4] Health check...")
    # Extra wait to let lifespan hooks fully complete
    time.sleep(2)
    d = get("/health")
    status = d.get("status", "?")
    ok(f"Backend healthy — status={status}")

    # Also check /ready (Ollama + DB)
    try:
        r = get("/ready", timeout=10)
        ollama_ok  = r.get("ollama") == "reachable"
        model_ok   = r.get("model_available", False)
        db_ok      = r.get("database") == "connected"
        info(f"Ollama: {'reachable' if ollama_ok else 'UNREACHABLE'}  |  "
             f"Model: {'available' if model_ok else 'MISSING'}  |  "
             f"DB: {'connected' if db_ok else 'ERROR'}")
        if not ollama_ok:
            fail("Ollama is not running. Start it with: ollama serve")
            sys.exit(1)
    except Exception as e:
        warn(f"/ready check failed (non-fatal): {e}")

# ── Step 3: Create project ────────────────────────────────────────────────────

def create_project():
    p(BOLD, f"\n[3/4] Creating project: '{PROJECT_NAME}'...")
    resp = post("/projects/create-and-run", {
        "name": PROJECT_NAME,
        "description": PROJECT_DESC,
    })
    project_id = resp.get("id") or resp.get("project_id")
    if not project_id:
        fail(f"No project_id in response: {resp}")
        sys.exit(1)
    ok(f"Project created: {project_id}")
    info(f"Description: {PROJECT_DESC}")
    info("Pipeline started in background (DomainResearch → Clarifying → QA_PENDING)")
    return project_id

# ── Step 4: Poll status ───────────────────────────────────────────────────────

def poll_status(project_id):
    p(BOLD, f"\n[4/4] Polling status (every {POLL_INTERVAL}s, up to {POLL_TIMEOUT}s)...")
    info("Ollama will run DomainResearch then generate clarification questions")
    info("This takes 3–10 minutes on CPU-only hardware\n")

    deadline    = time.time() + POLL_TIMEOUT
    last_state  = None
    poll_count  = 0
    start_time  = time.time()

    while time.time() < deadline:
        poll_count += 1
        elapsed = int(time.time() - start_time)

        try:
            s = get(f"/workflow/{project_id}/status")
        except Exception as e:
            warn(f"[{elapsed}s] Status fetch failed: {e} — retrying...")
            time.sleep(POLL_INTERVAL)
            continue

        state    = s.get("state", "?")
        stage    = s.get("current_stage") or "—"
        done     = len(s.get("completed_stages", []))
        total    = s.get("total_stages", 0)
        progress = s.get("progress_percent", 0)
        status   = s.get("status", "?")

        if state != last_state:
            print()
            p(BOLD, f"  ┌─ State changed at {elapsed}s ─────────────────────")
            p(BOLD, f"  │  state    : {state}")
            print(f"  │  status   : {status}")
            print(f"  │  stage    : {stage}")
            print(f"  │  progress : {done}/{total} stages  ({progress}%)")
            if s.get("failed_stage"):
                fail(f"  │  FAILED at: {s['failed_stage']}")
                if s.get("failure_reason"):
                    fail(f"  │  reason  : {s['failure_reason']}")
            p(BOLD, f"  └──────────────────────────────────────────────────")
            last_state = state
        else:
            print(f"  [{elapsed:4d}s] state={state}  stage={stage}  progress={done}/{total}", end="\r")

        if state == "qa_pending":
            print()
            ok(f"Pipeline reached qa_pending in {elapsed}s!")
            return s, True

        if state == "failed":
            print()
            fail(f"Pipeline FAILED at stage: {s.get('failed_stage', '?')}")
            fail(f"Reason: {s.get('failure_reason', 'unknown')}")
            return s, False

        time.sleep(POLL_INTERVAL)

    print()
    warn(f"Timed out after {POLL_TIMEOUT}s. Last state: {last_state}")
    return None, False

# ── Show QA questions ─────────────────────────────────────────────────────────

def show_questions(project_id):
    print()
    p(BOLD, "  ── Clarification Questions (generated by Ollama) ──")
    try:
        qa = get(f"/workflow/{project_id}/qa")
        questions = qa.get("questions", [])
        if not questions:
            warn("No questions found in QA session")
            return
        ok(f"{len(questions)} question(s) generated:")
        print()
        for i, q in enumerate(questions, 1):
            prio = q.get("priority", "?")
            text = q.get("question", "?")
            opts = q.get("options") or []
            color = GREEN if prio == "CRITICAL" else CYAN
            print(f"  {color}Q{i} [{prio}]{RESET}: {text}")
            if opts:
                for o in opts[:4]:
                    label = o.get("label") or o.get("value", "")
                    print(f"         • {label}")
            print()
    except Exception as e:
        warn(f"Could not fetch questions: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"{BOLD}{'='*60}")
    print("  AI DevOS — Start + Create + Monitor")
    print(f"{'='*60}{RESET}")

    backend_proc = start_backend()
    try:
        check_health()
        project_id = create_project()
        status, reached_qa = poll_status(project_id)

        print(f"\n{BOLD}{'='*60}{RESET}")
        if reached_qa:
            p(GREEN, f"{BOLD}  PIPELINE WORKING ✓")
            print(f"{RESET}  Project ID : {project_id}")
            print(f"  State      : qa_pending (waiting for your answers)")
            print(f"  Frontend   : http://localhost:5173")
            print(f"  API docs   : http://localhost:8000/docs")
            show_questions(project_id)
        else:
            p(RED, f"{BOLD}  PIPELINE FAILED ✗")
            if status:
                print(f"{RESET}  Last state : {status.get('state')}")
                print(f"  Failed at  : {status.get('failed_stage')}")
        print(f"{BOLD}{'='*60}{RESET}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        print("\nShutting down backend...")
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
        print("Done.")


if __name__ == "__main__":
    main()
