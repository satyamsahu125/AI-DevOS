from __future__ import annotations

from typing import Any

from ..context.agent_context import AgentContext
from ..memory.memory_summary import MemorySummary
from .prompt_formatter import PromptFormatter
from .prompt_package import PromptPackage
from .prompt_resolver import PromptResolver
from .prompt_template import PromptTemplate
from .prompt_validator import PromptValidationException, PromptValidator
from .prompt_variables import PromptVariables


class PromptBuilderRuntime:
    """Builds a PromptPackage from a template, variables, and runtime context."""

    def __init__(self, validator: PromptValidator | None = None, formatter: PromptFormatter | None = None, resolver: PromptResolver | None = None) -> None:
        self.validator = validator or PromptValidator()
        self.formatter = formatter or PromptFormatter()
        self.resolver = resolver or PromptResolver()

    def build(self, template: PromptTemplate, variables: PromptVariables, context: AgentContext | None = None, memory_summary: MemorySummary | None = None) -> PromptPackage:
        if template is None:
            raise PromptValidationException("template is required")
        if variables is None:
            raise PromptValidationException("variables are required")

        resolved = self.resolver.resolve(template, variables)
        formatted = self.formatter.format(
            system_prompt=resolved.system,
            user_prompt=resolved.user,
            context_prompt=self._serialize_context(context),
            rules_prompt=resolved.rules,
            memory_prompt=self._serialize_memory(memory_summary),
        )

        combined_prompt = "\n\n".join(
            part for part in [formatted["system_prompt"], formatted["user_prompt"], formatted["context_prompt"], formatted["rules_prompt"], formatted["memory_prompt"]] if part
        )
        self.validator.validate(template, variables, combined_prompt)

        package = PromptPackage(
            package_id=f"{template.template_id}:{template.stage}",
            stage=template.stage,
            system_prompt=formatted["system_prompt"],
            user_prompt=formatted["user_prompt"],
            context_prompt=formatted["context_prompt"],
            rules_prompt=formatted["rules_prompt"],
            memory_prompt=formatted["memory_prompt"],
            metadata={
                "agent": template.agent,
                "version": template.version,
                "context": bool(context),
                "memory": bool(memory_summary),
            },
        )
        package.estimated_tokens = self.validator.estimate_tokens(combined_prompt)
        return package

    def _serialize_context(self, context: AgentContext | None) -> str:
        if context is None:
            return ""
        agent_name = getattr(context, "agent_name", "") or getattr(context, "project_name", "") or "runtime"
        task = getattr(context, "task", "") or getattr(context, "requirements", "") or "task"
        return f"AgentContext(agent={agent_name}, task={task})"

    def _serialize_memory(self, memory_summary: MemorySummary | None) -> str:
        if memory_summary is None:
            return ""
        return f"MemorySummary(summary={memory_summary.summary})"
