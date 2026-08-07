from .context import AgentContext, ContextBuilder, ContextManager

__all__ = ["AgentContext", "ContextBuilder", "ContextManager"]


def __getattr__(name: str):
    if name == "ContextBuilderRuntime":
        from .context_builder_runtime import ContextBuilderRuntime
        return ContextBuilderRuntime
    raise AttributeError(name)
