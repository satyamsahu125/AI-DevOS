from __future__ import annotations

from ..artifacts.contracts import (
    STAGE_CONTRACTS,
    GenericArtifact,
    ArtifactContractViolation,
    get_contract,
)
from ..shared.models.stage_artifact import StageArtifact
from .runtime_context import RuntimeContext
from .runtime_result import RuntimeResult
from .runtime_validation import RuntimeValidator
from ..agents.factory import AgentFactory


class AgentRuntime:
    """Executes a single stage through the documented agent factory."""

    def __init__(self, factory: AgentFactory | None = None, validator: RuntimeValidator | None = None) -> None:
        self.factory = factory or AgentFactory()
        self.validator = validator or RuntimeValidator()

    def execute(self, stage_name: str, content: str) -> RuntimeResult:
        context = RuntimeContext(stage_name=stage_name, content=content)
        agent = self.factory.create(stage_name)
        artifact = agent.execute(context)

        # Validate artifact output against stage contract
        self._validate_artifact(stage_name, artifact)

        self.validator.validate(artifact)
        return RuntimeResult(artifact=artifact, success=True, message="stage executed")

    def _validate_artifact(self, stage_name: str, artifact: Any) -> None:
        """Validate artifact output against the stage's Pydantic contract.

        Raises ArtifactContractViolation if validation fails — the stage
        will be marked Failed and not marked complete.
        """
        # Extract dict output from artifact (handle both dict and object with structured_content)
        output_dict = self._extract_output_dict(artifact)
        if not output_dict:
            return  # Nothing to validate

        contract = get_contract(stage_name)
        try:
            contract.model_validate(output_dict)
        except Exception as e:
            raise ArtifactContractViolation(
                f"Agent output for stage '{stage_name}' failed contract validation: {e}"
            ) from e

    def _extract_output_dict(self, artifact: Any) -> dict[str, Any] | None:
        """Extract a dict from the artifact for validation."""
        if isinstance(artifact, dict):
            return artifact
        # Check for structured_content attribute (common in StageArtifact)
        structured = getattr(artifact, "structured_content", None)
        if isinstance(structured, dict):
            return structured
        content = getattr(artifact, "content", None)
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                import json
                return json.loads(content)
            except Exception:
                pass
        return None
