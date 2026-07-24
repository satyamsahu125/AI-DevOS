import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.validation_gate import RuntimeValidationGate


class RuntimeValidationGateTests(unittest.TestCase):
    def test_generates_pass_report_for_current_backend_runtime(self) -> None:
        gate = RuntimeValidationGate(root=Path(__file__).resolve().parents[1])
        report = gate.validate()

        self.assertEqual(report.overall_status, "PASS")
        self.assertTrue(report.implementation_allowed)
        self.assertIn("Runtime Validation", report.results)
        self.assertIn("Overall: PASS", report.to_text())

    def test_marks_failure_when_required_module_is_missing(self) -> None:
        gate = RuntimeValidationGate(root=Path(__file__).resolve().parents[1])
        report = gate.validate(required_modules=["app.not_a_real_module"])

        self.assertEqual(report.overall_status, "FAIL")
        self.assertFalse(report.implementation_allowed)
        self.assertIn("Import Validation", report.results)


if __name__ == "__main__":
    unittest.main()
