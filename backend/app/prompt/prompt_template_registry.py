from __future__ import annotations

from pathlib import Path
from typing import Any

from .prompt_template import PromptTemplate


class PromptTemplateRegistry:
    """Loads prompt templates from backend/prompts for the runtime."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "prompts"
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def initialize(self) -> None:
        self._templates = {}
        for agent_dir in sorted(self.root.iterdir()):
            if not agent_dir.is_dir():
                continue
            for file_name in ("system.md", "user.md", "rules.md"):
                path = agent_dir / file_name
                if path.exists():
                    self._templates[(agent_dir.name, file_name)] = PromptTemplate(
                        template_id=path.stem,
                        agent=agent_dir.name,
                        stage=agent_dir.name,
                        version="1",
                        system=path.read_text(encoding="utf-8"),
                        user=path.read_text(encoding="utf-8"),
                        rules=path.read_text(encoding="utf-8"),
                    )

    def load_all(self) -> dict[tuple[str, str], PromptTemplate]:
        self.initialize()
        return dict(self._templates)

    def get(self, agent: str, stage: str) -> PromptTemplate | None:
        return self._templates.get((agent, stage))

    def get_latest(self, agent: str, stage: str) -> PromptTemplate | None:
        return self.get(agent, stage)

    def exists(self, agent: str, stage: str) -> bool:
        return self.get(agent, stage) is not None

    def validate(self) -> None:
        if not self._templates:
            raise ValueError("no templates loaded")

    def shutdown(self) -> None:
        self._templates.clear()
