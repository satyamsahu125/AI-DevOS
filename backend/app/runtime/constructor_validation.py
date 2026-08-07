from __future__ import annotations

import inspect
from typing import Any

from ..shared.exceptions import DependencyException


class ConstructorValidation:
    """Validates that agent constructors can be satisfied."""

    def validate(self, constructor: Any, dependencies: dict[str, Any]) -> None:
        if constructor is None:
            raise DependencyException("constructor is required")
        signature = inspect.signature(constructor)
        for name, parameter in signature.parameters.items():
            if name in {"self", "cls", "args", "kwargs"}:
                continue
            if parameter.default is inspect.Parameter.empty and name not in dependencies:
                raise DependencyException(f"missing dependency for constructor parameter: {name}")
