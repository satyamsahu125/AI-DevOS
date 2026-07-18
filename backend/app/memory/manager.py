from __future__ import annotations

from pathlib import Path


class MemoryManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

    def initialize(self, project_name: str) -> Path:
        project_root = self.root / project_name.replace(" ", "-").lower()
        project_root.mkdir(parents=True, exist_ok=True)
        return project_root

    def store(self, key: str, value: str) -> None:
        path = self.root / f"{key}.txt"
        path.write_text(value, encoding="utf-8")

    def load(self, key: str) -> str | None:
        path = self.root / f"{key}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
