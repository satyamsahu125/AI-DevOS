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
        }
        return mapping.get(normalized, normalized)
