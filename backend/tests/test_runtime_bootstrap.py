import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.registry import AgentRegistry
from app.kernel.bootstrap import Bootstrap
from app.core.service_registry import ServiceRegistry
from app.core.runtime import Runtime


class RuntimeBootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_runtime_with_registered_services(self) -> None:
        bootstrap = Bootstrap()
        runtime = bootstrap.initialize()

        self.assertIsInstance(runtime, Runtime)
        self.assertIsInstance(runtime.service_registry, ServiceRegistry)
        self.assertIsNotNone(runtime.container)
        self.assertTrue(runtime.service_registry.has("configuration_manager"))

    def test_agent_registry_tracks_documented_agents(self) -> None:
        registry = AgentRegistry()
        registry.register("product_owner", "ProductOwnerAgent")

        self.assertTrue(registry.has("product_owner"))
        self.assertEqual(registry.resolve("product_owner"), "ProductOwnerAgent")


if __name__ == "__main__":
    unittest.main()
