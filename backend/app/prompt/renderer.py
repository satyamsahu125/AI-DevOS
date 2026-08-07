from __future__ import annotations

from .template import PromptTemplate


class PromptRenderer:
    """Render prompt templates with simple variable substitution."""

    def render(self, template: PromptTemplate, variables: dict[str, object] | None = None) -> str:
        variables = variables or {}
        rendered = template.system_template.format_map({**variables, **{"__name__": template.name}})
        return rendered
