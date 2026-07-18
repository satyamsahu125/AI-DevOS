import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


class APISmokeTests(unittest.TestCase):
    def test_health_and_project_routes(self) -> None:
        client = TestClient(app)

        health_response = client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "healthy"})

        project_response = client.post(
            "/projects",
            json={"name": "API Smoke", "description": "Smoke test project"},
        )
        self.assertEqual(project_response.status_code, 200)
        self.assertIn("project", project_response.json())
        self.assertTrue(project_response.json()["success"])


if __name__ == "__main__":
    unittest.main()
