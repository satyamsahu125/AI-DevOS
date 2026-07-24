import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.llm_manager import LLMManager
from app.llm.llm_request import LLMRequest


class FakeProvider:
    def generate(self, request):
        return type(
            "Response",
            (),
            {"response_id": "r1", "provider": request.provider, "model": request.model, "content": "ok", "usage": {"prompt": 1, "completion": 1, "total": 2}, "finish_reason": "stop", "latency": 0.0, "metadata": {}, "created_at": None},
        )()


class LLMManagerTests(unittest.TestCase):
    def test_execute_returns_normalized_response(self) -> None:
        manager = LLMManager(provider=FakeProvider())
        request = LLMRequest(request_id="1", provider="fake", model="gpt-test")
        response = manager.execute(request)
        self.assertEqual("ok", response.content)
        self.assertEqual("fake", response.provider)

    def test_validation_rejects_invalid_request(self) -> None:
        manager = LLMManager()
        with self.assertRaises(Exception):
            manager.execute(LLMRequest(request_id="1", provider="", model=""))


if __name__ == "__main__":
    unittest.main()
