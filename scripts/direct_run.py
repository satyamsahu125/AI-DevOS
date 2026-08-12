"""
direct_run.py
Directly imports WorkflowManager and runs MoodSync without going through HTTP.
Run from: F:\AI-DevOS3\backend\
"""
import sys, os, json, time, logging
from pathlib import Path

# ── logging setup ─────────────────────────────────────────────────────────────
LOG_FILE = Path("F:/AI-DevOS3/direct_run.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("direct_run")

# ── path setup ────────────────────────────────────────────────────────────────
BACKEND = Path("F:/AI-DevOS3/backend")
sys.path.insert(0, str(BACKEND))

log.info("=== direct_run.py starting ===")
log.info("Python: %s", sys.version)
log.info("CWD: %s", os.getcwd())

# ── import kernel + managers ──────────────────────────────────────────────────
log.info("Importing kernel…")
from app.kernel.kernel import AIKernel
from app.workspace.manager import WorkspaceManager
from app.project.manager import ProjectManager

kernel = AIKernel()
kernel.start()
container = kernel.container

log.info("AIKernel started. Container type: %s", type(container).__name__)

# Resolve singletons from container
workspace_manager: WorkspaceManager = container.workspace_manager
project_manager: ProjectManager     = container.project_manager
workflow_manager                    = container.workflow_manager

log.info("Managers resolved OK: proj_mgr=%s wf_mgr=%s", type(project_manager).__name__, type(workflow_manager).__name__)

# ── create project ────────────────────────────────────────────────────────────
PROJECT_NAME = "MoodSync"
DESCRIPTION  = (
    "A mood-tracking journaling app where users log daily emotions with emoji tags, "
    "get AI-generated insights about emotional patterns over time, set weekly mood goals, "
    "and receive personalized coping strategy suggestions based on their history. "
    "Backend: FastAPI + SQLite. Frontend: React + TypeScript."
)

from app.shared.dto.project_request import ProjectRequest

log.info("Creating project '%s'…", PROJECT_NAME)
req = ProjectRequest(name=PROJECT_NAME, description=DESCRIPTION)
project = project_manager.create_project(req)
project_id = getattr(project, "id", None) or getattr(project, "project_id", None) or str(project)
log.info("Project created: %s", project_id)

# ── run pipeline (skip Q&A for speed) ─────────────────────────────────────────
log.info("Starting pipeline (skip_qa=True)…")
t0 = time.time()

try:
    result = workflow_manager.run(
        project_id=project_id,
        request=DESCRIPTION,
        skip_qa=True,
    )
    elapsed = time.time() - t0
    log.info("Pipeline finished in %.1f s", elapsed)
    log.info("Result: success=%s state=%s message=%s",
             getattr(result, "success", "?"),
             getattr(result, "state",   "?"),
             getattr(result, "message", "?"))
except Exception as exc:
    elapsed = time.time() - t0
    log.error("Pipeline raised exception after %.1f s: %s", elapsed, exc, exc_info=True)

# ── collect artifacts ─────────────────────────────────────────────────────────
WORKSPACE = Path("F:/AI-DevOS3/temp-workspace") / project_id
artifacts_root = WORKSPACE / "artifacts"
report = {
    "project_id": project_id,
    "elapsed_seconds": round(elapsed, 1),
    "pipeline_result": {
        "success": getattr(result, "success", None) if "result" in dir() else None,
        "state":   str(getattr(result, "state",   None)) if "result" in dir() else None,
        "message": getattr(result, "message", None) if "result" in dir() else None,
        "completed_stages": getattr(result, "completed_stages", []) if "result" in dir() else [],
        "failed_stage":     getattr(result, "failed_stage", None) if "result" in dir() else None,
    },
    "artifacts": {},
    "generated_files": [],
}

log.info("--- Collecting artifacts from %s ---", artifacts_root)
if artifacts_root.exists():
    for scope_dir in sorted(artifacts_root.iterdir()):
        if scope_dir.is_dir():
            scope = scope_dir.name
            report["artifacts"][scope] = {}
            for jf in sorted(scope_dir.glob("*.json")):
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    report["artifacts"][scope][jf.name] = data
                    keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                    log.info("  artifact %s/%s  keys=%s", scope, jf.name, keys)
                except Exception as ex:
                    log.warning("  ARTIFACT READ ERROR %s/%s: %s", scope, jf.name, ex)
else:
    # Fall back to legacy flat artifacts dir
    legacy = WORKSPACE
    for jf in sorted(legacy.glob("artifacts/*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            report["artifacts"].setdefault("legacy", {})[jf.name] = data
            log.info("  legacy artifact %s  keys=%s", jf.name,
                     list(data.keys()) if isinstance(data, dict) else type(data).__name__)
        except Exception as ex:
            log.warning("  LEGACY ARTIFACT ERROR %s: %s", jf.name, ex)

# ── list generated code files ─────────────────────────────────────────────────
project_code_dir = WORKSPACE / "project"
log.info("--- Generated code files in %s ---", project_code_dir)
if project_code_dir.exists():
    for f in sorted(project_code_dir.rglob("*")):
        if f.is_file() and "_attempt_" not in f.name:
            rel  = str(f.relative_to(project_code_dir))
            size = f.stat().st_size
            report["generated_files"].append({"path": rel, "bytes": size})
            log.info("  %s  (%d bytes)", rel, size)
else:
    log.warning("project code dir missing: %s", project_code_dir)

# ── project.json ──────────────────────────────────────────────────────────────
pjson_path = WORKSPACE / "project.json"
if pjson_path.exists():
    pjson = json.loads(pjson_path.read_text(encoding="utf-8"))
    report["project_json"] = pjson
    log.info("project.json: state=%s stages=%s",
             pjson.get("state"), pjson.get("stages_completed"))
else:
    log.warning("project.json missing")

# ── save report ───────────────────────────────────────────────────────────────
report_path = Path("F:/AI-DevOS3/direct_run_report.json")
report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
log.info("Report saved → %s", report_path)
log.info("=== direct_run.py done ===")
