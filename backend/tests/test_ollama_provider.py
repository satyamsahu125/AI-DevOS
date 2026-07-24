import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.llm_request import LLMRequest
from app.llm.providers.ollama_provider import OllamaProvider


class OllamaProviderTests(unittest.TestCase):
    def test_health_reports_reachable_when_server_responds(self) -> None:
        provider = OllamaProvider(base_url="http://example.test")
        with patch("app.llm.providers.ollama_provider.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{"models": [{"name": "demo"}]}'
            health = provider.health()
        self.assertTrue(health.reachable)
        self.assertEqual("ollama", provider.provider_name())

    def test_execute_maps_ollama_response_to_llm_response(self) -> None:
        provider = OllamaProvider(base_url="http://example.test")
        request = LLMRequest(request_id="1", provider="ollama", model="demo")
        with patch("app.llm.providers.ollama_provider.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{"response": "ok", "done": true, "prompt_eval_count": 2, "eval_count": 3}'
            response = provider.execute(request)
        self.assertEqual("ok", response.content)
        self.assertEqual("demo", response.model)


if __name__ == "__main__":
    unittest.main()
