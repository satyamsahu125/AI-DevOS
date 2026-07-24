import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.llm_request import LLMRequest
from app.llm.providers import LLMProvider, ProviderCapabilities, ProviderHealth, ProviderValidation


class DummyProvider(LLMProvider):
    def initialize(self) -> None:
        return None

    def execute(self, request: LLMRequest):
        return type("Response", (), {"content": "ok", "provider": request.provider, "model": request.model})()

    def stream(self, request: LLMRequest):
        yield type("Chunk", (), {"content": "ok"})()

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider="dummy")

    def shutdown(self) -> None:
        return None

    def validate(self, request: LLMRequest) -> None:
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        return "dummy"

    def supported_models(self) -> list[str]:
        return ["dummy-model"]

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, supported_models=["dummy-model"])


class LLMProviderInterfaceTests(unittest.TestCase):
    def test_provider_interface_contract(self) -> None:
        provider = DummyProvider()
        request = LLMRequest(request_id="1", provider="dummy", model="dummy-model")
        provider.validate(request)
        health = provider.health()
        self.assertEqual("dummy", provider.provider_name())
        self.assertTrue(health.reachable)


if __name__ == "__main__":
    unittest.main()
