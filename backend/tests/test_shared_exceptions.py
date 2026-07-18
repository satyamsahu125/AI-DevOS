import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.shared.exceptions.base import ApplicationException
from app.shared.exceptions.configuration import ConfigurationException
from app.shared.exceptions.dependency import DependencyException
from app.shared.exceptions.workflow import WorkflowException
from app.shared.exceptions.execution import ExecutionException
from app.shared.exceptions.session import SessionException
from app.shared.exceptions.memory import MemoryException
from app.shared.exceptions.artifact import ArtifactException
from app.shared.exceptions.review import ReviewException
from app.shared.exceptions.llm import LLMException


class SharedExceptionsTests(unittest.TestCase):
    def test_base_exception_preserves_message(self) -> None:
        exc = ApplicationException("boom")

        self.assertEqual(str(exc), "boom")
        self.assertEqual(exc.message, "boom")

    def test_specific_exceptions_are_application_exceptions(self) -> None:
        exceptions = [
            ConfigurationException,
            DependencyException,
            WorkflowException,
            ExecutionException,
            SessionException,
            MemoryException,
            ArtifactException,
            ReviewException,
            LLMException,
        ]

        for exc_type in exceptions:
            self.assertTrue(issubclass(exc_type, ApplicationException))


if __name__ == "__main__":
    unittest.main()
