from __future__ import annotations

import logging
import http.client
import urllib.error
from uuid import uuid4

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from ..config.manager import ConfigurationManager
from .cost_tracker import CostTracker, get_shared_cost_tracker
from .factory import LLMFactory
from .llm_request import LLMRequest
from .llm_response import LLMResponse
from .providers.provider_health import ProviderHealth

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    ConnectionError,
    TimeoutError
)


class LLMManager:
    """Small manager that uses the configured provider (see providers/ollama_provider.py) for text generation."""

    def __init__(
        self,
        config_manager: ConfigurationManager | None = None,
        factory: LLMFactory | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        """Load configuration and build the provider matching settings.llm.provider."""
        self._config_manager = config_manager or ConfigurationManager()
        self._factory = factory or LLMFactory()
        self._settings = self._config_manager.load()
        self._provider = self._build_provider()
        self.cost_tracker = cost_tracker or get_shared_cost_tracker()
        self._current_project_id: str = ""
        self._current_stage: str = ""
        logger.debug("llm manager ready: provider=%s model=%s", self._settings.llm.provider, self._settings.llm.model)

    def set_context(self, project_id: str, stage: str) -> None:
        """Called by WorkflowEngine before each stage."""
        self._current_project_id = project_id
        self._current_stage = stage

    def _build_provider(self):
        llm = self._settings.llm
        # Pick the right API key for the chosen provider
        provider_name = llm.provider.lower()
        if provider_name == "claude":
            api_key = getattr(llm, "claude_api_key", "") or llm.bedrock_api_key
        elif provider_name == "gemini":
            api_key = getattr(llm, "gemini_api_key", "") or llm.bedrock_api_key
        else:
            api_key = ""
        return self._factory.create_provider(
            llm.provider,
            base_url=llm.base_url,
            api_key=api_key,
            bedrock_api_key=llm.bedrock_api_key,
            bedrock_region=llm.bedrock_region,
            timeout=getattr(llm, "timeout", 1200),
        )

    @property
    def configured_model(self) -> str:
        """Return the model name configured for the active provider."""
        return self._settings.llm.model

    @property
    def configured_provider(self) -> str:
        """Return the provider name currently active."""
        return self._settings.llm.provider

    def reconfigure(self, provider: str | None = None, model: str | None = None, **provider_kwargs: str) -> None:
        """Switch the active provider/model at runtime (no process restart required).

        provider_kwargs are passed straight through to LLMConfig for fields
        like bedrock_api_key/bedrock_region/base_url -- unknown keys are
        ignored by pydantic's default (non-extra) validation error, so
        callers should only pass fields LLMConfig actually declares.
        """
        current = self._settings.llm
        updated = current.model_copy(update={
            "provider": provider or current.provider,
            "model": model or current.model,
            **provider_kwargs,
        })
        self._settings.llm = updated
        self._provider = self._build_provider()
        logger.info("llm manager reconfigured: provider=%s model=%s", updated.provider, updated.model)

    def health(self) -> ProviderHealth:
        """Return the configured provider's reachability/health (see providers/provider_health.py)."""
        return self._provider.health()

    def is_model_available(self) -> bool:
        """Return whether the configured model is among the provider's currently loaded models."""
        return self.configured_model in self._provider.supported_models()

    def generate_requirements(self, request: str) -> str:
        """Ask the configured provider to draft structured requirements text for request."""
        logger.debug("generate_requirements: request=%s", request)
        response = self.generate_text(
            request,
            system_prompt=(
                "You are a Product Owner. Write clear, structured software requirements "
                "(goals, user stories, and acceptance criteria) for the request below."
            ),
        )
        return response.content

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
        stage: str = "",
        agent: str = "",
        project_id: str = "",
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate a completion for prompt (optionally under system_prompt) via the configured provider.

        stage/agent/project_id are optional attribution for CostTracker --
        omit them and the call is still tracked, just unattributed.
        max_tokens overrides the global config value when set; callers such as
        WriteQAReportAction/WriteDeploymentAction that generate large outputs
        use this to avoid Ollama truncating mid-response.
        """
        settings = self._settings
        resolved_model = model or settings.llm.model
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        resolved_num_ctx = getattr(settings.llm, "num_ctx", 8192)
        logger.debug(
            "generate_text: model=%s prompt_len=%s stage=%s agent=%s max_tokens=%s num_ctx=%s json_mode=%s",
            resolved_model, len(prompt), stage, agent, resolved_max_tokens, resolved_num_ctx, json_mode,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        request = LLMRequest(
            request_id=str(uuid4()),
            provider=settings.llm.provider,
            model=resolved_model,
            messages=messages,
            temperature=settings.llm.temperature,
            max_tokens=resolved_max_tokens,
            num_ctx=resolved_num_ctx,
            json_mode=json_mode,
        )
        response = self._provider.execute(request)
        self._record_cost(resolved_model, response, stage, agent, project_id)
        return response

    def _record_cost(self, model: str, response: LLMResponse, stage: str, agent: str, project_id: str) -> None:
        """Record response's token usage and latency with CostTracker, tolerating response shapes without them."""
        usage = getattr(response, "usage", None) or {}
        latency = getattr(response, "latency", None) or 0.0
        eff_project_id = project_id or self._current_project_id
        eff_stage = stage or self._current_stage
        self.cost_tracker.record(
            project_id=eff_project_id,
            stage=eff_stage,
            agent=agent,
            provider=self.configured_provider,
            model=model,
            prompt_tokens=int(usage.get("prompt", 0)),
            completion_tokens=int(usage.get("completion", 0)),
            latency_ms=latency * 1000,
            success=True,
        )
