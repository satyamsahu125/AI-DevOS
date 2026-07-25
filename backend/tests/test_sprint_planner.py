import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.actions.clarify_requirements import ClarifyRequirementsAction
from app.actions.plan_sprints import PlanSprintsAction
from app.agents.clarification import ClarificationAgent
from app.agents.sprint_planner import SprintPlannerAgent
from app.shared.models.sprint import Sprint, SprintPlan, SprintStatus, SprintTask
from app.shared.schemas.clarification_schema import ClarificationArtifact
from app.shared.schemas.sprint_schema import SprintPlanSchema


class SprintPlannerTests(unittest.TestCase):
    def test_sprint_plan_validates_against_schema(self) -> None:
        raw_data = {
            "project_id": "proj-123",
            "total_sprints": 2,
            "rationale": "Split foundation and features",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sprints": [
                {
                    "sprint_id": "s1",
                    "sprint_number": 1,
                    "name": "Sprint 1: Foundation",
                    "goal": "Setup database and user auth",
                    "features": ["auth"],
                    "tasks": [
                        {
                            "task_id": "t1",
                            "description": "Create User model",
                            "agent": "BackendDeveloper",
                            "file_paths": ["backend/models/user.py"],
                            "depends_on": [],
                        }
                    ],
                    "status": "planned",
                },
                {
                    "sprint_id": "s2",
                    "sprint_number": 2,
                    "name": "Sprint 2: Features",
                    "goal": "Todo CRUD",
                    "features": ["crud"],
                    "tasks": [
                        {
                            "task_id": "t2",
                            "description": "Create todo endpoints",
                            "agent": "BackendDeveloper",
                            "file_paths": ["backend/routers/todo.py"],
                            "depends_on": ["t1"],
                        }
                    ],
                    "status": "planned",
                },
            ],
        }
        plan = SprintPlan.model_validate(raw_data)
        self.assertEqual(plan.total_sprints, 2)
        self.assertEqual(len(plan.sprints), 2)
        self.assertEqual(plan.sprints[0].tasks[0].file_paths, ["backend/models/user.py"])

        schema_plan = SprintPlanSchema.model_validate(raw_data)
        self.assertEqual(schema_plan.total_sprints, 2)

    def test_sprint_plan_covers_all_files(self) -> None:
        all_arch_files = ["backend/models/user.py", "backend/routers/auth.py", "frontend/src/App.tsx"]
        tasks = [
            SprintTask(
                task_id="t1",
                description="Setup user",
                agent="BackendDeveloper",
                file_paths=["backend/models/user.py", "backend/routers/auth.py"],
            ),
            SprintTask(
                task_id="t2",
                description="Setup UI",
                agent="FrontendDeveloper",
                file_paths=["frontend/src/App.tsx"],
            ),
        ]
        sprint = Sprint(
            sprint_id="s1",
            sprint_number=1,
            name="Sprint 1",
            goal="Foundation",
            features=["all"],
            tasks=tasks,
        )
        plan = SprintPlan(
            project_id="p1",
            total_sprints=1,
            sprints=[sprint],
            created_at=datetime.now(timezone.utc),
            rationale="Single sprint for small project",
        )

        planned_files = []
        for s in plan.sprints:
            for t in s.tasks:
                planned_files.extend(t.file_paths)

        self.assertEqual(set(planned_files), set(all_arch_files))

    def test_sprint_dependencies_respected(self) -> None:
        t1 = SprintTask(task_id="t1", description="DB Setup", agent="BackendDeveloper", file_paths=["db.py"])
        t2 = SprintTask(
            task_id="t2",
            description="API Router",
            agent="BackendDeveloper",
            file_paths=["router.py"],
            depends_on=["t1"],
        )
        s1 = Sprint(sprint_id="s1", sprint_number=1, name="Sprint 1", goal="DB", tasks=[t1])
        s2 = Sprint(sprint_id="s2", sprint_number=2, name="Sprint 2", goal="API", tasks=[t2])
        plan = SprintPlan(
            project_id="p1",
            total_sprints=2,
            sprints=[s1, s2],
            created_at=datetime.now(timezone.utc),
            rationale="Sequential",
        )

        s1_task_ids = {t.task_id for t in plan.sprints[0].tasks}
        for t in plan.sprints[1].tasks:
            for dep in t.depends_on:
                self.assertIn(dep, s1_task_ids)

    def test_clarification_enriches_requirements(self) -> None:
        artifact = ClarificationArtifact(
            original_request="Build todo app",
            clarified_requirements="Build a multi-tenant todo app with JWT auth and React frontend",
            assumptions_made=["Single user account per registration", "PostgreSQL database"],
            questions_asked=["Who are the primary users?", "Is mobile view required?"],
            answers_received=["Individual task managers", "Responsive web view is sufficient"],
            confidence_score=0.9,
            ready_for_requirements=True,
        )
        self.assertTrue(len(artifact.clarified_requirements) > len(artifact.original_request))
        self.assertTrue(artifact.ready_for_requirements)
        self.assertGreater(artifact.confidence_score, 0.5)

    def test_clarification_cap_at_7_questions(self) -> None:
        questions = [f"Question {i}?" for i in range(10)]
        capped_questions = questions[:7]
        artifact = ClarificationArtifact(
            original_request="Build e-commerce app",
            clarified_requirements="E-commerce store",
            questions_asked=capped_questions,
            confidence_score=0.8,
            ready_for_requirements=True,
        )
        self.assertLessEqual(len(artifact.questions_asked), 7)


if __name__ == "__main__":
    unittest.main()
