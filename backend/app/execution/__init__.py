__all__ = [
    "AgentRuntime",
    "ExecutionEngine",
    "DocumentedExecutionEngine",
    "ExecutionMetrics",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionValidation",
    "ExecutionManager",
    "ExecutionRecovery",
    "RecoveryCheckpoint",
    "RecoveryPolicy",
    "RecoveryResult",
    "RecoveryValidation",
    "RuntimeContext",
    "RuntimeResult",
    "StageExecutor",
    "StageExecutionResult",
    "StageExecutionStatus",
    "StageValidation",
]


def __getattr__(name: str):
    if name in {"AgentRuntime", "ExecutionEngine", "DocumentedExecutionEngine"}:
        from .agent_runtime import AgentRuntime
        from .engine import ExecutionEngine
        from .execution_engine import ExecutionEngine as DocumentedExecutionEngine
        mapping = {"AgentRuntime": AgentRuntime, "ExecutionEngine": ExecutionEngine, "DocumentedExecutionEngine": DocumentedExecutionEngine}
        return mapping[name]
    if name == "ExecutionMetrics":
        from .execution_metrics import ExecutionMetrics
        return ExecutionMetrics
    if name == "ExecutionResult":
        from .execution_result import ExecutionResult
        return ExecutionResult
    if name == "ExecutionStatus":
        from .execution_status import ExecutionStatus
        return ExecutionStatus
    if name == "ExecutionValidation":
        from .execution_validation import ExecutionValidation
        return ExecutionValidation
    if name == "ExecutionManager":
        from .manager import ExecutionManager
        return ExecutionManager
    if name == "ExecutionRecovery":
        from .execution_recovery import ExecutionRecovery
        return ExecutionRecovery
    if name == "RecoveryCheckpoint":
        from .recovery_checkpoint import RecoveryCheckpoint
        return RecoveryCheckpoint
    if name == "RecoveryPolicy":
        from .recovery_policy import RecoveryPolicy
        return RecoveryPolicy
    if name == "RecoveryResult":
        from .recovery_result import RecoveryResult
        return RecoveryResult
    if name == "RecoveryValidation":
        from .recovery_validation import RecoveryValidation
        return RecoveryValidation
    if name == "RuntimeContext":
        from .runtime_context import RuntimeContext
        return RuntimeContext
    if name == "RuntimeResult":
        from .runtime_result import RuntimeResult
        return RuntimeResult
    if name == "StageExecutor":
        from .stage_executor import StageExecutor
        return StageExecutor
    if name == "StageExecutionResult":
        from .stage_execution_result import StageExecutionResult
        return StageExecutionResult
    if name == "StageExecutionStatus":
        from .stage_execution_status import StageExecutionStatus
        return StageExecutionStatus
    if name == "StageValidation":
        from .stage_validation import StageValidation
        return StageValidation
    raise AttributeError(name)
