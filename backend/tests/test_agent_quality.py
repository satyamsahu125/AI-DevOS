"""Unit tests for agent quality overhaul (Q&A, ProductOwner, Architect, Security, Designer)."""

import unittest

from app.shared.schemas.architecture_schema import APIEndpoint, ModuleSpec, SystemArchitecture
from app.shared.schemas.clarification_schema import ClarificationArtifact, ScaleProfile


class AgentQualityTests(unittest.TestCase):
    def test_calculator_qa_has_non_requirements(self) -> None:
        """Q&A for calculator must have explicit_non_requirements and scale_profile."""
        schema = ClarificationArtifact(
            original_request="Build a calculator",
            explicit_non_requirements=[
                "No authentication or user accounts required",
                "No database or data persistence required",
            ],
            scale_profile=ScaleProfile(
                user_count="under_100",
                auth_needed=False,
                database_needed=False,
                infrastructure_tier="static_frontend_only",
            ),
        )
        self.assertFalse(schema.scale_profile.auth_needed)
        self.assertFalse(schema.scale_profile.database_needed)
        self.assertEqual(schema.scale_profile.infrastructure_tier, "static_frontend_only")
        self.assertTrue(any("auth" in r.lower() for r in schema.explicit_non_requirements))

    def test_architect_schema_has_no_json_strings(self) -> None:
        """Architecture fields must be typed objects not strings."""
        schema = SystemArchitecture(
            modules=[
                ModuleSpec(
                    name="calculator",
                    purpose="Handles arithmetic operations",
                    layer="presentation",
                    technology="React",
                    dependencies=[],
                    exports=["Calculator"],
                    files=["src/Calculator.tsx"],
                )
            ],
            api_endpoints=[
                APIEndpoint(
                    path="/api/v1/calculate",
                    method="POST",
                    description="Calculate expression",
                    auth_required=False,
                )
            ],
            data_models=[],
            tech_stack={"frontend": "React/Vite"},
        )
        self.assertIsInstance(schema.modules, list)
        self.assertIsInstance(schema.modules[0], ModuleSpec)
        self.assertEqual(schema.modules[0].name, "calculator")
        self.assertEqual(schema.modules[0].technology, "React")
        self.assertIsInstance(schema.api_endpoints, list)
        self.assertEqual(schema.api_endpoints[0].method, "POST")


if __name__ == "__main__":
    unittest.main()
