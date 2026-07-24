import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependency_container import DependencyInjectionContainer
from app.core.service_lifetime import ServiceLifetime


class ServiceA:
    pass


class ServiceB:
    def __init__(self, service_a: ServiceA) -> None:
        self.service_a = service_a


class DependencyContainerTests(unittest.TestCase):
    def test_register_and_resolve_services_with_constructor_injection(self) -> None:
        container = DependencyInjectionContainer()
        container.register_singleton("service_a", ServiceA)
        container.register_transient("service_b", ServiceB, dependencies=["service_a"])

        service_b = container.resolve("service_b")

        self.assertIsInstance(service_b, ServiceB)
        self.assertIsInstance(service_b.service_a, ServiceA)

    def test_singletons_are_cached_and_transients_are_new_instances(self) -> None:
        container = DependencyInjectionContainer()
        container.register_singleton("service_a", ServiceA)
        container.register_transient("service_b", ServiceB, dependencies=["service_a"])

        first = container.resolve("service_a")
        second = container.resolve("service_a")
        self.assertIs(first, second)

        first_b = container.resolve("service_b")
        second_b = container.resolve("service_b")
        self.assertIsNot(first_b, second_b)

    def test_register_scoped_uses_documented_lifetime(self) -> None:
        container = DependencyInjectionContainer()
        container.register_scoped("service_a", ServiceA)

        self.assertEqual(container.resolve("service_a"), container.resolve("service_a"))
        self.assertEqual(container.get_lifetime("service_a"), ServiceLifetime.Scoped)


if __name__ == "__main__":
    unittest.main()
