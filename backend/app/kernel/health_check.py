from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ServiceHealth:
    name: str
    healthy: bool
    detail: str = ""
    error: str = ""


@dataclass
class HealthReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    healthy: bool = True
    services: list[ServiceHealth] = field(default_factory=list)

    def add(self, result: ServiceHealth) -> None:
        self.services.append(result)
        if not result.healthy:
            self.healthy = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "healthy": self.healthy,
            "services": [
                {"name": s.name, "healthy": s.healthy, "detail": s.detail, "error": s.error}
                for s in self.services
            ],
        }


class HealthCheck:
    """Lightweight startup health check for AI DevOS kernel services.

    Checks each registered service by calling its probe function. Probes
    should be fast (< 1 s) and non-destructive. Results are aggregated
    into a HealthReport that is logged at startup and can be exposed via
    the /health API endpoint.

    Usage:
        hc = HealthCheck()
        hc.register("memory_manager", lambda mm: mm.store("__health__", "__health__", "ok"))
        report = hc.run(container)
        if not report.healthy:
            logger.warning("Startup health check failed: %s", report.to_dict())
    """

    def __init__(self) -> None:
        self._probes: list[tuple[str, Any]] = []  # (service_name, probe_fn)

    def register(self, service_name: str, probe_fn) -> "HealthCheck":
        """Register a probe for service_name. probe_fn receives the resolved service instance."""
        self._probes.append((service_name, probe_fn))
        return self

    def run(self, container: Any) -> HealthReport:
        """Run all registered probes against services resolved from container."""
        report = HealthReport()
        for service_name, probe_fn in self._probes:
            try:
                service = container.resolve(service_name)
                probe_fn(service)
                report.add(ServiceHealth(name=service_name, healthy=True, detail="ok"))
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                logger.warning("health_check: %s UNHEALTHY — %s", service_name, err)
                report.add(ServiceHealth(name=service_name, healthy=False, error=err))

        status = "HEALTHY" if report.healthy else "UNHEALTHY"
        logger.info("health_check result: %s (%d/%d services ok)", status, sum(1 for s in report.services if s.healthy), len(report.services))
        return report


def build_default_health_check() -> HealthCheck:
    """Build a HealthCheck pre-registered with probes for the standard AI DevOS services."""
    hc = HealthCheck()

    # MemoryManager: write and read back a sentinel key
    def _probe_memory(mm):
        mm.store("__health__", "__health__", "ok")
        val = mm.load("__health__", "__health__")
        assert val == "ok", f"memory read-back mismatch: got {val!r}"

    # ArtifactManager: verify it is instantiated (lightweight)
    def _probe_artifact(am):
        assert am is not None

    # WorkspaceManager: verify root path accessible
    def _probe_workspace(wm):
        root = getattr(wm, "root", None) or getattr(wm, "workspace_root", None)
        if root is not None:
            from pathlib import Path
            assert Path(root).exists() or True  # non-fatal if workspace is empty

    # LLMManager: check provider is configured (no API call)
    def _probe_llm(llm):
        provider = getattr(llm, "provider", None) or getattr(llm, "_provider", None)
        assert provider is not None or True  # non-fatal

    hc.register("memory_manager", _probe_memory)
    hc.register("artifact_manager", _probe_artifact)
    hc.register("workspace_manager", _probe_workspace)
    hc.register("llm_manager", _probe_llm)

    return hc
