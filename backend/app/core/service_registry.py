from __future__ import annotations

from typing import Any

from ..shared.exceptions import DependencyException
from .registry_validation import RegistryValidation
from .service_descriptor import ServiceDescriptor


class ServiceRegistry:
    """Central registry for runtime services and managers."""

    def __init__(self) -> None:
        self.services: dict[str, ServiceDescriptor] = {}
        self.managers: dict[str, ServiceDescriptor] = {}
        self.providers: dict[str, ServiceDescriptor] = {}
        self.registries: dict[str, ServiceDescriptor] = {}
        self.runtime_components: dict[str, ServiceDescriptor] = {}

    def register(self, descriptor: ServiceDescriptor) -> ServiceDescriptor:
        RegistryValidation.validate_name(descriptor.name)
        RegistryValidation.validate_descriptor(descriptor)
        self.services[descriptor.name] = descriptor
        if descriptor.kind == "manager":
            self.managers[descriptor.name] = descriptor
        elif descriptor.kind == "provider":
            self.providers[descriptor.name] = descriptor
        elif descriptor.kind == "registry":
            self.registries[descriptor.name] = descriptor
        else:
            self.runtime_components[descriptor.name] = descriptor
        return descriptor

    def register_service(self, name: str, factory: Any | None = None, metadata: dict[str, Any] | None = None) -> ServiceDescriptor:
        return self.register(ServiceDescriptor(name=name, kind="service", factory=factory, metadata=metadata or {}))

    def register_manager(self, name: str, factory: Any | None = None, metadata: dict[str, Any] | None = None) -> ServiceDescriptor:
        return self.register(ServiceDescriptor(name=name, kind="manager", factory=factory, metadata=metadata or {}))

    def register_provider(self, name: str, factory: Any | None = None, metadata: dict[str, Any] | None = None) -> ServiceDescriptor:
        return self.register(ServiceDescriptor(name=name, kind="provider", factory=factory, metadata=metadata or {}))

    def register_registry(self, name: str, factory: Any | None = None, metadata: dict[str, Any] | None = None) -> ServiceDescriptor:
        return self.register(ServiceDescriptor(name=name, kind="registry", factory=factory, metadata=metadata or {}))

    def register_runtime_component(self, name: str, factory: Any | None = None, metadata: dict[str, Any] | None = None) -> ServiceDescriptor:
        return self.register(ServiceDescriptor(name=name, kind="runtime_component", factory=factory, metadata=metadata or {}))

    def resolve(self, name: str) -> ServiceDescriptor:
        if not self.has(name):
            raise DependencyException(f"service {name} is not registered")
        return self.services[name]

    def has(self, name: str) -> bool:
        return name in self.services

    def list_services(self) -> list[str]:
        return sorted(self.services)

    def validate(self) -> None:
        if not self.services:
            raise DependencyException("service registry is empty")
