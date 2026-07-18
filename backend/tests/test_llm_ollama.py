import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.manager import LLMManager
from app.llm.request import LLMRequest


class LLMOllamaTests(unittest.TestCase):
    @patch("app.llm.providers.ollama.urlopen")
    def test_manager_uses_ollama_provider_when_available(self, mock_urlopen) -> None:
        class ResponseStub:
            status = 200

            def __enter__(self) -> "ResponseStub":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return b'{"response": "hello from ollama", "done": true, "prompt_eval_count": 3, "eval_count": 2}'

        mock_urlopen.return_value = ResponseStub()

        manager = LLMManager()
        response = manager.generate_text("hello", system_prompt="You are helpful")

        self.assertEqual(response.content, "hello from ollama")
        self.assertEqual(response.model, "qwen2.5-coder:7b")
        self.assertEqual(mock_urlopen.call_args[0][0].full_url, "http://localhost:11434/api/generate")


if __name__ == "__main__":
    unittest.main()
