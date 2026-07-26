from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ValidationReport:
    """Structured validation report used by the runtime approval gate."""

    root: Path
    results: dict[str, str] = field(default_factory=dict)
    implementation_allowed: bool = True

    @property
    def overall_status(self) -> str:
        return "PASS" if self.implementation_allowed else "FAIL"

    def to_text(self) -> str:
        lines = ["AI DevOS Validation Report", "========================", ""]
        for name, status in self.results.items():
            lines.append(f"{name}: {status}")
        lines.append("")
        lines.append(f"Overall: {self.overall_status}")
        return "\n".join(lines)


class RuntimeValidationGate:
    """Perform repository-level validation for the runtime approval gate."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1]

    def validate(self, required_modules: list[str] | None = None) -> ValidationReport:
        report = ValidationReport(root=self.root)
        report.results["Repository Validation"] = self._check_repository()
        report.results["Folder Validation"] = self._check_folders()
        report.results["Import Validation"] = self._check_imports(required_modules)
        report.results["Constructor Validation"] = self._check_constructors()
        report.results["Method Validation"] = self._check_methods()
        report.results["Runtime Validation"] = self._check_runtime()
        report.results["Duplicate Validation"] = self._check_duplicates()

        report.implementation_allowed = all(
            status == "PASS" for status in report.results.values()
        )
        return report

    def _check_repository(self) -> str:
        return "PASS" if (self.root / "app").exists() else "FAIL"

    def _check_folders(self) -> str:
        required = ["app", "app/core", "app/execution", "app/workflow", "app/prompt", "app/context", "app/memory"]
        missing = [path for path in required if not (self.root / path).exists()]
        return "PASS" if not missing else "FAIL"

    def _check_imports(self, required_modules: list[str] | None = None) -> str:
        modules = required_modules or ["app.core.runtime", "app.workflow.transition_manager", "app.prompt.prompt_builder_runtime"]
        for module in modules:
            try:
                importlib.import_module(module)
            except Exception:
                return "FAIL"
        return "PASS"

    def _check_constructors(self) -> str:
        try:
            from app.core.runtime import Runtime
            Runtime(service_registry=None, container=None, agent_registry=None)  # type: ignore[arg-type]
        except Exception:
            return "FAIL"
        return "PASS"

    def _check_methods(self) -> str:
        try:
            from app.core.runtime import Runtime
            methods = [name for name in dir(Runtime) if not name.startswith("_")]
            return "PASS" if methods else "FAIL"
        except Exception:
            return "FAIL"

    def _check_runtime(self) -> str:
        try:
            from app.core.runtime import Runtime
            from app.core.service_registry import ServiceRegistry
            from app.core.dependency_container import DependencyContainer
            from app.agents.registry import AgentRegistry
            Runtime(service_registry=ServiceRegistry(), container=DependencyContainer(), agent_registry=AgentRegistry())
        except Exception:
            return "FAIL"
        return "PASS"

    def _check_duplicates(self) -> str:
        files = [path for path in self.root.rglob("*.py") if path.stem not in {"__init__"}]
        grouped: dict[tuple[Path, str], int] = {}
        for path in files:
            key = (path.parent, path.stem)
            grouped[key] = grouped.get(key, 0) + 1
        if any(count > 1 for count in grouped.values()):
            return "FAIL"
        return "PASS"
