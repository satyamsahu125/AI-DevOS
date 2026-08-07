from __future__ import annotations

from pathlib import Path

from .prompt_template import PromptTemplate


class TemplateLoader:
    """Loads prompt templates from disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "prompts"

    def load(self, agent: str, stage: str) -> PromptTemplate | None:
        path = self.root / agent / f"{stage}.md"
        if not path.exists():
            return None
        return PromptTemplate(
            template_id=path.stem,
            agent=agent,
            stage=stage,
            version="1",
            system=path.read_text(encoding="utf-8"),
            user=path.read_text(encoding="utf-8"),
            rules=path.read_text(encoding="utf-8"),
        )
