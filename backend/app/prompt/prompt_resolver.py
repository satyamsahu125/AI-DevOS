from __future__ import annotations

import re
from typing import Any

from .prompt_template import PromptTemplate
from .prompt_variables import PromptVariables


class PromptResolver:
    """Resolves placeholders in prompt templates against variable values."""

    def resolve(self, template: PromptTemplate, variables: PromptVariables) -> PromptTemplate:
        def replace(text: str) -> str:
            return re.sub(r"\{\{(.*?)\}\}", lambda match: str(variables.get(match.group(1).strip(), "")), text)

        resolved = PromptTemplate(
            template_id=template.template_id,
            agent=template.agent,
            stage=template.stage,
            version=template.version,
            system=replace(template.system),
            user=replace(template.user),
            rules=replace(template.rules),
            variables=list(template.variables),
            metadata=dict(template.metadata),
        )
        return resolved
