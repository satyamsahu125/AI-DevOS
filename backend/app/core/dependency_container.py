from __future__ import annotations

import inspect
from typing import Any, Callable

from ..shared.exceptions import DependencyException
from .dependency_container_exception import DependencyContainerException
from .dependency_descriptor import DependencyDescriptor
from .dependency_validation import DependencyValidation
from .service_lifetime import ServiceLifetime
from .service_registration import ServiceRegistration
from .service_registry import ServiceRegistry


class DependencyInjectionContainer:
    """Constructs and resolves runtime services from the service registry."""

    def __init__(self, registry: ServiceRegistry | None = None) -> None:
        self.registry = registry or ServiceRegistry()
        self._registrations: dict[str, ServiceRegistration] = {}
        self._singletons: dict[str, Any] = {}
        self._scoped_instances: dict[str, Any] = {}

    def register(self, descriptor: DependencyDescriptor | ServiceRegistration) -> ServiceRegistration | DependencyDescriptor:
        if isinstance(descriptor, ServiceRegistration):
            return self._register_registration(descriptor)
        if isinstance(descriptor, DependencyDescriptor):
            return self._register_descriptor(descriptor)
        raise DependencyException("dependency descriptor is required")

    def register_singleton(self, key: str, implementation: Any, dependencies: list[str] | None = None) -> ServiceRegistration:
        return self._register_registration(ServiceRegistration(key=key, implementation=implementation, lifetime=ServiceLifetime.Singleton, dependencies=dependencies or []))

    def register_scoped(self, key: str, implementation: Any, dependencies: list[str] | None = None) -> ServiceRegistration:
        return self._register_registration(ServiceRegistration(key=key, implementation=implementation, lifetime=ServiceLifetime.Scoped, dependencies=dependencies or []))

    def register_transient(self, key: str, implementation: Any, dependencies: list[str] | None = None) -> ServiceRegistration:
        return self._register_registration(ServiceRegistration(key=key, implementation=implementation, lifetime=ServiceLifetime.Transient, dependencies=dependencies or []))

    def resolve(self, name: str) -> Any:
        if name in self._singletons:
            return self._singletons[name]
        if name in self._scoped_instances:
            return self._scoped_instances[name]

        registration = self._registrations.get(name)
        if registration is None:
            if self.registry.has(name):
                return self._resolve_from_registry(name)
            raise DependencyException(f"dependency {name} is not registered")

        self._validate_dependencies(registration)
        instance = self._create_instance(registration)
        if registration.lifetime == ServiceLifetime.Singleton:
            self._singletons[name] = instance
        elif registration.lifetime == ServiceLifetime.Scoped:
            self._scoped_instances[name] = instance
        return instance

    def get_lifetime(self, name: str) -> ServiceLifetime:
        registration = self._registrations.get(name)
        if registration is None:
            return ServiceLifetime.Singleton
        return registration.lifetime

    def has(self, name: str) -> bool:
        return name in self._registrations or self.registry.has(name)

    def validate(self) -> None:
        if not self._registrations and not self.registry.services:
            raise DependencyException("dependency container is empty")
        for registration in self._registrations.values():
            self._validate_dependencies(registration)

    def _register_registration(self, registration: ServiceRegistration) -> ServiceRegistration:
        DependencyValidation.validate_name(registration.key)
        self._registrations[registration.key] = registration
        return registration

    def _register_descriptor(self, descriptor: DependencyDescriptor) -> DependencyDescriptor:
        DependencyValidation.validate_name(descriptor.name)
        self._registrations[descriptor.name] = ServiceRegistration(
            key=descriptor.name,
            implementation=descriptor.factory,
            lifetime=ServiceLifetime.Singleton,
            dependencies=[],
        )
        return descriptor

    def _resolve_from_registry(self, name: str) -> Any:
        descriptor = self.registry.resolve(name)
        factory = descriptor.factory
        if factory is None:
            if name == "configuration_manager":
                from ..config.manager import ConfigurationManager
                factory = ConfigurationManager
            elif name == "llm_manager":
                from ..llm.manager import LLMManager
                factory = LLMManager
            elif name == "artifact_manager":
                from ..artifact.manager import ArtifactManager
                factory = ArtifactManager
            else:
                raise DependencyException(f"service {name} has no factory")
        if inspect.isclass(factory):
            instance = self._instantiate_class(factory, [])
        else:
            instance = self._invoke_callable(factory, [])
        self._singletons[name] = instance
        return instance

    def _create_instance(self, registration: ServiceRegistration) -> Any:
        implementation = registration.implementation
        if implementation is None:
            raise DependencyException(f"dependency {registration.key} has no implementation")
        if inspect.isclass(implementation):
            return self._instantiate_class(implementation, registration.dependencies)
        if callable(implementation):
            return self._invoke_callable(implementation, registration.dependencies)
        return implementation

    def _instantiate_class(self, target: type[Any], dependencies: list[str]) -> Any:
        if not hasattr(target, "__init__"):
            raise DependencyContainerException(f"dependency {target.__name__} is not constructible")
        signature = inspect.signature(target.__init__)
        args: dict[str, Any] = {}
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name in {"self", "cls"}:
                continue
            if parameter_name in dependencies:
                args[parameter_name] = self.resolve(parameter_name)
                continue
            if parameter.default is not inspect.Parameter.empty:
                continue
            if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                continue
            if parameter_name in self._registrations:
                args[parameter_name] = self.resolve(parameter_name)
                continue
            if self.registry.has(parameter_name):
                args[parameter_name] = self.resolve(parameter_name)
                continue
            raise DependencyContainerException(f"dependency {parameter_name} is missing for {target.__name__}")
        return target(**args)

    def _invoke_callable(self, factory: Callable[..., Any], dependencies: list[str]) -> Any:
        signature = inspect.signature(factory)
        args: dict[str, Any] = {}
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name in dependencies:
                args[parameter_name] = self.resolve(parameter_name)
                continue
            if parameter.default is not inspect.Parameter.empty:
                continue
            if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                continue
            if parameter_name in self._registrations:
                args[parameter_name] = self.resolve(parameter_name)
                continue
            if self.registry.has(parameter_name):
                args[parameter_name] = self.resolve(parameter_name)
                continue
            if parameter_name not in {"self", "cls"}:
                raise DependencyContainerException(f"dependency {parameter_name} is missing for factory")
        return factory(**args)

    def _validate_dependencies(self, registration: ServiceRegistration) -> None:
        if registration.key in registration.dependencies:
            raise DependencyContainerException("circular dependency detected")
        for dependency_name in registration.dependencies:
            if dependency_name not in self._registrations and not self.registry.has(dependency_name):
                raise DependencyContainerException(f"missing dependency {dependency_name}")
        self._validate_graph(registration.key, set(), set())

    def _validate_graph(self, name: str, visiting: set[str], visited: set[str]) -> None:
        if name in visiting:
            raise DependencyContainerException("circular dependency detected")
        if name in visited:
            return
        registration = self._registrations.get(name)
        if registration is None:
            return
        visiting.add(name)
        for dependency_name in registration.dependencies:
            self._validate_graph(dependency_name, visiting, visited)
        visiting.remove(name)
        visited.add(name)


class DependencyContainer(DependencyInjectionContainer):
    """Backward-compatible alias for the documented dependency container."""

    pass
