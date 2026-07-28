"""
run_project.py — Creates MoodSync project, starts the pipeline, polls until
completion, then dumps all artifact files and server logs.
Run from: F:\AI-DevOS3\
"""
import json
import time
import urllib.request
import urllib.error
import os
import sys
from pathlib import Path

BASE = "http://localhost:8000"
WORKSPACE = Path("F:/AI-DevOS3/temp-workspace")

def api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}
    except Exception as ex:
        return {"error": str(ex)}

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open("F:/AI-DevOS3/run_project.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── 1. Create project ────────────────────────────────────────────────────────
log("Creating MoodSync project...")
proj = api("POST", "/projects", {
    "name": "MoodSync",
    "description": (
        "A mood-tracking journaling app where users log daily emotions with emoji tags, "
        "get AI-generated insights about emotional patterns over time, set weekly mood goals, "
        "and receive personalized coping strategy suggestions based on their history. "
        "Backend: FastAPI + SQLite. Frontend: React + TypeScript."
    )
})
log(f"Project response: {json.dumps(proj, indent=2)}")

project_id = proj.get("project_id") or proj.get("id") or proj.get("project", {}).get("id")
if not project_id:
    # Try listing and finding ours
    projects = api("GET", "/projects")
    log(f"Projects list: {json.dumps(projects, indent=2)}")
    sys.exit(1)

log(f"Project ID: {project_id}")

# ── 2. Start workflow (skip Q&A for speed) ───────────────────────────────────
log("Starting workflow (skip_qa=true)...")
start = api("POST", "/workflow/start", {
    "project_id": project_id,
    "request": (
        "Build MoodSync: A mood-tracking journaling app. "
        "Users log daily emotions with emoji tags. "
        "AI generates insights about emotional patterns. "
        "Users set weekly mood goals and get personalized coping strategies. "
        "Backend: FastAPI + SQLite. Frontend: React + TypeScript."
    ),
    "skip_qa": True
})
log(f"Start response: {json.dumps(start, indent=2)}")

# ── 3. Poll until done ───────────────────────────────────────────────────────
terminal = {"done", "deployable", "failed", "sprint_blocked", "paused"}
max_polls = 240   # 240 * 15s = 60 min max
poll = 0

while poll < max_polls:
    time.sleep(15)
    poll += 1
    status = api("GET", f"/workflow/{project_id}/status")
    state  = status.get("state", "unknown")
    stage  = status.get("current_stage", "-")
    pct    = status.get("progress_percent", 0)
    sprint = status.get("current_sprint", "-")
    log(f"Poll {poll:3d}: state={state} stage={stage} sprint={sprint} progress={pct}%")

    requires_action = status.get("requires_user_action", False)
    action_needed   = status.get("action_needed", "")

    # Auto-approve design review
    if state == "design_review_pending" or (requires_action and action_needed == "review_design"):
        log("Design review pending — auto-approving...")
        apr = api("POST", f"/workflow/{project_id}/approve-design", {
            "approved": True,
            "feedback": "Looks great, proceed."
        })
        log(f"Design approval: {json.dumps(apr, indent=2)}")
        # Resume pipeline
        cont = api("POST", f"/workflow/{project_id}/continue", {})
        log(f"Continue: {json.dumps(cont, indent=2)}")
        continue

    if state in terminal:
        log(f"Pipeline reached terminal state: {state}")
        break

log(f"\n{'='*60}")
log("PIPELINE COMPLETE — collecting artifacts and logs")
log(f"{'='*60}\n")

# ── 4. Collect artifacts ─────────────────────────────────────────────────────
proj_workspace = WORKSPACE / project_id
artifacts_root  = proj_workspace / "artifacts"

summary = {}
summary["project_id"] = project_id
summary["final_status"] = api("GET", f"/workflow/{project_id}/status")
summary["artifacts"] = {}

if artifacts_root.exists():
    for scope_dir in sorted(artifacts_root.iterdir()):
        if scope_dir.is_dir():
            scope = scope_dir.name
            summary["artifacts"][scope] = {}
            for jf in sorted(scope_dir.glob("*.json")):
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    summary["artifacts"][scope][jf.name] = data
                    log(f"  artifact: {scope}/{jf.name} — keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                except Exception as ex:
                    log(f"  artifact READ ERROR: {scope}/{jf.name}: {ex}")
else:
    log(f"WARNING: artifacts dir not found: {artifacts_root}")

# ── 5. List generated code files ─────────────────────────────────────────────
project_code_dir = proj_workspace / "project"
summary["generated_files"] = []
if project_code_dir.exists():
    for f in sorted(project_code_dir.rglob("*")):
        if f.is_file() and not f.name.startswith("_attempt_"):
            rel = str(f.relative_to(project_code_dir))
            size = f.stat().st_size
            summary["generated_files"].append({"path": rel, "size_bytes": size})
            log(f"  code: {rel} ({size} bytes)")
else:
    log(f"WARNING: project code dir not found: {project_code_dir}")

# ── 6. Check project.json ─────────────────────────────────────────────────────
pjson_path = proj_workspace / "project.json"
if pjson_path.exists():
    pjson = json.loads(pjson_path.read_text(encoding="utf-8"))
    summary["project_json"] = pjson
    log(f"\nproject.json state={pjson.get('state')} stages_completed={pjson.get('stages_completed')}")

# ── 7. Save full report ───────────────────────────────────────────────────────
report_path = Path("F:/AI-DevOS3/run_report.json")
report_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
log(f"\nFull report saved to: {report_path}")
log("DONE.")
