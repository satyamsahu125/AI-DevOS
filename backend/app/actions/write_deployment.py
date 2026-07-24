from __future__ import annotations

from ..prompt.devops_builder import DevOpsPromptBuilder
from ..shared.schemas.deployment_schema import DeploymentArtifact
from .base_action import LLMAction


class WriteDeploymentAction(LLMAction):
    """DevOps's action: produces a structured DeploymentArtifact."""

    name = "WriteDeployment"
    description = "Produce deployment steps, environment configuration, and a rollback plan."
    schema_model = DeploymentArtifact
    system_prompt = (
        "You are a DevOps Engineer producing deployment configuration. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "steps (list of objects with name/command/description), "
        "environment (object mapping env var name to value), rollback_plan (string)."
    )

    def __init__(self, prompt_builder: DevOpsPromptBuilder | None = None) -> None:
        """Wire the DevOps prompt builder this action uses."""
        super().__init__(prompt_builder or DevOpsPromptBuilder())
