from __future__ import annotations


class AgentResolver:
    """Resolves a workflow stage name to an agent name."""

    def resolve(self, stage_name: str) -> str:
        normalized = stage_name.lower().replace(" ", "_").replace("-", "_")
        mapping = {
            "productowner": "product_owner",
            "product_owner": "product_owner",
            "architect": "architect",
            "backenddeveloper": "backend",
            "backend_developer": "backend",
            "frontenddeveloper": "frontend",
            "frontend_developer": "frontend",
            "qa": "qa",
            "devops": "devops",
            "reviewer": "reviewer",
            "strategicreview": "strategic_review",
            "strategic_review": "strategic_review",
            "designer": "designer",
            "security": "security",
            "filestructureplanner": "file_planner",
            "file_structure_planner": "file_planner",
            "file_planner": "file_planner",
            "document": "document",
            "retro": "retro",
            "clarification": "clarification",
            "clarificationagent": "clarification",
            "sprintplanner": "sprint_planner",
            "sprint_planner": "sprint_planner",
            "sprintplanning": "sprint_planner",
            "sprint_planning": "sprint_planner",
            "scrummaster": "scrum_master",
            "scrum_master": "scrum_master",
            # Sprint-internal agents — called directly by WorkflowManager, not
            # via engine.run_stage(), but listed here so factory.create() works
            # for tests and future tooling.
            "tech_lead": "tech_lead",
            "techlead": "tech_lead",
            "bug_analyst": "bug_analyst",
            "buganalyst": "bug_analyst",
            "sprint_deploy": "sprint_deploy",
            "sprintdeploy": "sprint_deploy",
            "sprint_review": "sprint_review",
            "sprintreview": "sprint_review",
        }
        return mapping.get(normalized, normalized)
