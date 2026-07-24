from .builder import PromptBuilder
from .product_owner_builder import ProductOwnerPromptBuilder

__all__ = ["PromptBuilder", "ProductOwnerPromptBuilder"]


def __getattr__(name: str):
    if name == "PromptBuilderRuntime":
        from .prompt_builder_runtime import PromptBuilderRuntime
        return PromptBuilderRuntime
    if name == "PromptPackage":
        from .prompt_package import PromptPackage
        return PromptPackage
    if name == "PromptTemplate":
        from .prompt_template import PromptTemplate
        return PromptTemplate
    if name == "PromptTemplateRegistry":
        from .prompt_template_registry import PromptTemplateRegistry
        return PromptTemplateRegistry
    if name == "PromptValidationException":
        from .prompt_validator import PromptValidationException
        return PromptValidationException
    if name == "PromptValidator":
        from .prompt_validator import PromptValidator
        return PromptValidator
    if name == "PromptVariables":
        from .prompt_variables import PromptVariables
        return PromptVariables
    raise AttributeError(name)
