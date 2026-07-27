from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..shared.enums.project_state import ProjectState
from ..shared.models.sprint import SprintPlan, SprintStatus
from .layout import WorkspaceLayout
from .repository import WorkspaceRepository

logger = logging.getLogger(__name__)

# Per-project write lock — prevents concurrent update_project_json calls from
# corrupting project.json via interleaved read-modify-write sequences.
_project_locks: dict[str, threading.Lock] = {}
_project_locks_meta = threading.Lock()


def _get_project_lock(project_id: str) -> threading.Lock:
    with _project_locks_meta:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


class WorkspaceManager:
    """Owns every project's on-disk workspace, keyed by project_id (not name).

    Each project gets exactly one directory: `temp-workspace/{project_id}/`,
    containing the documented backend/frontend/docs/artifacts/temp
    subdirectories plus a `project.json` tracking file that records
    current_stage/stages_completed/status as the workflow progresses --
    the durable source of truth GET /projects/{project_id} reads from.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.getenv("WORKSPACE_ROOT", "temp-workspace"))
        self.layout = WorkspaceLayout(self.root)
        self.repository = WorkspaceRepository(self.root)

    def create_workspace(self, project_id: str, name: str = "", description: str = "") -> Path:
        """Create (idempotently) the workspace directory tree for project_id and seed project.json."""
        workspace_root = self.repository.create() / project_id
        workspace_root.mkdir(parents=True, exist_ok=True)
        for directory in self.layout.directories():
            (workspace_root / directory.name).mkdir(parents=True, exist_ok=True)

        project_json_path = workspace_root / "project.json"
        if not project_json_path.exists():
            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "project_id": project_id,
                "name": name,
                "description": description,
                "original_request": "",
                "state": ProjectState.EMPTY.value,
                "created_at": now,
                "updated_at": now,
                "clarification": {
                    "questions_asked": [],
                    "answers_received": [],
                    "complete": False,
                },
                "sprint_plan": None,
                "current_sprint": None,
                "current_sprint_number": 0,
                "total_sprints": 0,
                "completed_sprints": [],
                "stages_completed": [],
                "current_stage": None,
                "failed_at_stage": None,
                "failure_reason": None,
                "design_review": {
                    "status": "pending",
                    "user_feedback": None,
                    "iteration": 0,
                },
                "status": "active",
            }
            project_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return workspace_root

    def delete_workspace(self, project_id: str) -> bool:
        """Delete project_id's entire workspace directory tree. Returns whether it existed."""
        workspace_root = self.get_workspace_path(project_id)
        if not workspace_root.exists():
            return False
        shutil.rmtree(workspace_root)
        return True

    def get_workspace_path(self, project_id: str) -> Path:
        """Return the workspace directory for project_id (may not exist yet)."""
        return self.root / project_id

    def get_artifact_path(self, project_id: str, stage: str) -> Path:
        """Return the canonical markdown artifact path for project_id/stage."""
        return self.get_workspace_path(project_id) / "artifacts" / f"{stage}.md"

    def get_docs_path(self, project_id: str) -> Path:
        """Return the docs directory for project_id."""
        return self.get_workspace_path(project_id) / "docs"

    def load_project_json(self, project_id: str) -> dict | None:
        """Return the parsed project.json for project_id, or None if the workspace has none.

        Tolerates files corrupted by a previous write race: if ``json.loads`` raises
        ``JSONDecodeError``, we attempt to recover the first valid JSON object from
        the file via the streaming decoder, log a warning, and return what we can.
        """
        path = self.get_workspace_path(project_id) / "project.json"
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "project.json for %s is corrupted (JSONDecodeError) — attempting recovery",
                project_id,
            )
            try:
                obj, _ = json.JSONDecoder().raw_decode(raw)
                return obj
            except Exception as exc:
                logger.error("project.json recovery failed for %s: %s", project_id, exc)
                return None

    def update_project_json(self, project_id: str, updates: dict) -> None:
        """Merge updates into project.json atomically under a per-project lock.

        Uses a lock + write-to-temp-then-rename pattern so concurrent calls
        (e.g. engine._update_project_progress and _transition running in the
        same thread pool) never produce partially-overwritten or double-JSON files.
        """
        lock = _get_project_lock(project_id)
        with lock:
            path = self.get_workspace_path(project_id) / "project.json"
            data = self.load_project_json(project_id) or {"project_id": project_id}
            data.update(updates)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temp file in the same directory then rename so the
            # on-disk file is never in a partial state even if the process dies.
            tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def update_state(self, project_id: str, new_state: ProjectState) -> None:
        """Persist state change immediately."""
        state_val = new_state.value if isinstance(new_state, ProjectState) else str(new_state)
        self.update_project_json(project_id, {"state": state_val})

    def get_state(self, project_id: str) -> ProjectState:
        """Read project_id's current state, defaulting to ProjectState.EMPTY if absent."""
        data = self.load_project_json(project_id)
        if not data or "state" not in data or not data["state"]:
            return ProjectState.EMPTY
        try:
            return ProjectState(data["state"])
        except ValueError:
            return ProjectState.EMPTY

    def update_sprint_plan(self, project_id: str, sprint_plan: SprintPlan) -> None:
        """Persist sprint plan to project.json."""
        plan_dict = sprint_plan.model_dump(mode="json")
        self.update_project_json(
            project_id,
            {
                "sprint_plan": plan_dict,
                "total_sprints": sprint_plan.total_sprints,
            },
        )

    def get_sprint_plan(self, project_id: str) -> SprintPlan | None:
        """Retrieve SprintPlan from project.json if present.

        SprintPlanSchema.created_at is ``str = ""`` — the LLM often leaves it blank.
        SprintPlan.created_at is ``datetime`` — Pydantic rejects an empty string.
        Default the field to *now* before validating so an empty string never crashes
        the sprint execution phase.
        """
        data = self.load_project_json(project_id)
        if not data or not data.get("sprint_plan"):
            return None
        sprint_data = dict(data["sprint_plan"])
        if not sprint_data.get("created_at"):
            from datetime import datetime, timezone
            sprint_data["created_at"] = datetime.now(timezone.utc).isoformat()
        return SprintPlan.model_validate(sprint_data)

    def set_current_sprint(self, project_id: str, sprint_number: int) -> None:
        """Set current sprint number and update sprint status in sprint_plan."""
        data = self.load_project_json(project_id) or {}
        plan_data = data.get("sprint_plan")
        current_sprint_dict = None
        if plan_data and "sprints" in plan_data:
            for s in plan_data["sprints"]:
                if s.get("sprint_number") == sprint_number:
                    s["status"] = SprintStatus.IN_PROGRESS.value
                    if not s.get("started_at"):
                        s["started_at"] = datetime.now(timezone.utc).isoformat()
                    current_sprint_dict = s
                    break
        self.update_project_json(
            project_id,
            {
                "current_sprint_number": sprint_number,
                "current_sprint": current_sprint_dict,
                "sprint_plan": plan_data,
            },
        )

    def mark_sprint_complete(self, project_id: str, sprint_number: int) -> None:
        """Mark sprint as complete in completed_sprints and sprint_plan."""
        data = self.load_project_json(project_id) or {}
        completed = list(data.get("completed_sprints", []))
        if sprint_number not in completed:
            completed.append(sprint_number)
        plan_data = data.get("sprint_plan")
        if plan_data and "sprints" in plan_data:
            for s in plan_data["sprints"]:
                if s.get("sprint_number") == sprint_number:
                    s["status"] = SprintStatus.COMPLETE.value
                    s["completed_at"] = datetime.now(timezone.utc).isoformat()
                    break
        self.update_project_json(
            project_id,
            {
                "completed_sprints": completed,
                "sprint_plan": plan_data,
            },
        )

    def update_design_review(self, project_id: str, status: str, feedback: str | None = None) -> None:
        """Update design review status and feedback."""
        data = self.load_project_json(project_id) or {}
        dr = dict(data.get("design_review") or {})
        current_iter = dr.get("iteration")
        if not current_iter or current_iter < 1:
            current_iter = 1
        dr["status"] = status
        dr["user_feedback"] = feedback
        if status == "revision_requested":
            dr["iteration"] = current_iter + 1
        else:
            dr["iteration"] = current_iter
        self.update_project_json(project_id, {"design_review": dr})

    def save_approved_design(self, project_id: str, design: dict) -> None:
        """Save approved design to artifacts/design_approved.json and update project.json."""
        workspace_root = self.get_workspace_path(project_id)
        artifacts_dir = workspace_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        design_file = artifacts_dir / "design_approved.json"
        design_file.write_text(json.dumps(design, indent=2), encoding="utf-8")
        self.update_project_json(project_id, {
            "approved_design": design,
            "design_approved": True,
        })

    def load_approved_design(self, project_id: str) -> dict | None:
        """Load approved design from artifacts/design_approved.json or project.json."""
        workspace_root = self.get_workspace_path(project_id)
        design_file = workspace_root / "artifacts" / "design_approved.json"
        if design_file.exists():
            try:
                return json.loads(design_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(
                    "[WorkspaceManager.load_approved_design] Non-critical failure parsing design_approved.json for %s: %s",
                    project_id,
                    str(e),
                    exc_info=True,
                )
        project_data = self.load_project_json(project_id)
        if project_data and "approved_design" in project_data:
            return project_data["approved_design"]
        return None

    def save_qa_questions(self, project_id: str, questions: list[Any]) -> None:
        """Save Phase A questions to project.json."""
        serialized_q = []
        for q in questions:
            if hasattr(q, "model_dump"):
                serialized_q.append(q.model_dump(mode="json"))
            elif isinstance(q, dict):
                serialized_q.append(q)
            else:
                serialized_q.append({"index": len(serialized_q), "question": str(q)})

        qa_session = {
            "status": "pending",
            "current_question_index": 0,
            "total_questions": len(serialized_q),
            "answered": 0,
            "questions": serialized_q,
            "answers": [],
            "completed": False,
        }
        self.update_project_json(project_id, {"qa_session": qa_session})

    def save_qa_answer(self, project_id: str, q_index: int, answer: str) -> None:
        """Save a user answer for question at q_index."""
        data = self.load_project_json(project_id) or {}
        qa = dict(data.get("qa_session") or {})
        answers = list(qa.get("answers", []))

        existing_idx = None
        for i, a in enumerate(answers):
            if isinstance(a, dict) and a.get("question_index") == q_index:
                existing_idx = i
                break

        ans_obj = {
            "question_index": q_index,
            "answer": answer,
            "answered_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing_idx is not None:
            answers[existing_idx] = ans_obj
        else:
            answers.append(ans_obj)

        qa["answers"] = answers
        qa["answered"] = len(answers)
        qa["current_question_index"] = q_index + 1
        if qa["answered"] >= qa.get("total_questions", 0):
            qa["status"] = "in_progress"

        self.update_project_json(project_id, {"qa_session": qa})

    def skip_qa_question(self, project_id: str, q_index: int) -> None:
        """Skip optional question at q_index."""
        self.save_qa_answer(project_id, q_index, "Skipped")

    def get_qa_session(self, project_id: str) -> dict[str, Any]:
        """Retrieve Q&A session dictionary from project.json."""
        data = self.load_project_json(project_id) or {}
        return dict(
            data.get("qa_session")
            or {
                "status": "pending",
                "current_question_index": 0,
                "total_questions": 0,
                "answered": 0,
                "questions": [],
                "answers": [],
                "completed": False,
            }
        )

    def mark_qa_complete(self, project_id: str) -> None:
        """Mark Q&A session as complete."""
        data = self.load_project_json(project_id) or {}
        qa = dict(data.get("qa_session") or {})
        qa["status"] = "complete"
        qa["completed"] = True
        self.update_project_json(project_id, {"qa_session": qa})

    def create_sprint_folder(self, project_id: str, sprint_number: int) -> Path:
        """Idempotently create the artifact directory for *sprint_number*.

        Creates ``{workspace_root}/{project_id}/artifacts/sprint_{N}/``.
        Safe to call multiple times (``mkdir(exist_ok=True)``).

        Must be called before ScrumMasterAgent runs for each sprint so that
        :class:`~app.workspace.artifact_store.ArtifactStore` can write
        sprint-scoped artifacts into the correct directory.

        Returns the directory path.
        """
        sprint_dir = (
            self.get_workspace_path(project_id)
            / "artifacts"
            / f"sprint_{sprint_number}"
        )
        sprint_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "[WorkspaceManager] sprint artifact dir ready: %s", sprint_dir
        )
        return sprint_dir


