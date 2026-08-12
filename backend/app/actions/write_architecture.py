from __future__ import annotations

import logging
import re
from typing import Any

from ..prompt.architect_builder import ArchitectPromptBuilder
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from .base_action import LLMAction

logger = logging.getLogger(__name__)


class WriteArchitectureAction(LLMAction):
    """Architect's action: produces a structured ArchitectureArtifact."""

    name = "WriteArchitecture"
    description = "Design the system architecture: modules, API design, data models, and tech stack."
    schema_model = ArchitectureArtifact
    system_prompt = (
        "You are a Software Architect producing a system design. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys:\n"
        "  project_type (string — REQUIRED: one of 'web_fullstack', 'mobile_app', 'ml_pipeline', "
        "'cli_tool', 'data_pipeline', 'library', 'api_service', 'web_frontend', or another type "
        "that accurately describes the project — this controls which file structure ALL downstream "
        "agents will generate, so it must be correct),\n"
        "  implementation_approach (string), approach (string), layers (list of strings),\n"
        "  modules (list of ModuleSpec objects — each with: name (string), purpose (string), "
        "layer (string), technology (string), dependencies (list of strings), exports (list of strings), "
        "files (list of concrete file paths this module owns — e.g. ['app/main.py', 'app/routers/auth.py'] "
        "for a Python backend module, ['app/src/main/java/com/app/MainActivity.kt', "
        "'app/src/main/java/com/app/viewmodel/MainViewModel.kt'] for an Android module, "
        "['src/model.py', 'src/trainer.py'] for an ML module — NEVER leave files empty)),\n"
        "  api_endpoints (list of APIEndpoint objects with path, method, description, "
        "request_body, response_schema, auth_required, status_codes),\n"
        "  api_design (list of APIEndpoint objects),\n"
        "  data_models (list of DataModel objects with name, table_name, fields, relationships, indexes),\n"
        "  tech_stack (object mapping layer name to technology string — be specific: "
        "{'language': 'Kotlin', 'platform': 'Android', 'database': 'Room', 'networking': 'Retrofit'} "
        "for Android; {'language': 'Python', 'ml_framework': 'PyTorch', 'model_type': 'LSTM'} for ML; "
        "{'backend': 'FastAPI', 'database': 'PostgreSQL', 'frontend': 'React/Vite'} for web),\n"
        "  deployment_notes (string), scalability_notes (string),\n"
        "  out_of_scope (list of strings from PRD out_of_scope), anything_unclear (string)."
    )

    # Simplified system prompt used in the re-prompt pass when the full schema
    # parse fails.  Avoids nested objects entirely — status_codes as a plain
    # string, tech_stack as a flat dict — so even models that struggle with
    # complex nested JSON can produce a valid response.
    _SIMPLIFIED_SYSTEM_PROMPT = (
        "You are a Software Architect. Respond with ONLY a JSON object — no prose.\n"
        "Use this exact flat schema (no nested objects inside the lists):\n"
        "{\n"
        '  "project_type": "web_fullstack",\n'
        '  "implementation_approach": "one paragraph",\n'
        '  "layers": ["Presentation", "Business Logic", "Data"],\n'
        '  "modules": [\n'
        '    {"name": "Auth", "purpose": "JWT auth", "layer": "backend", '
        '"technology": "FastAPI", "files": ["app/auth.py"]}\n'
        "  ],\n"
        '  "api_endpoints": [\n'
        '    {"method": "POST", "path": "/api/login", "description": "user login", '
        '"auth_required": false, "status_codes": "200 OK, 401 Unauthorized"}\n'
        "  ],\n"
        '  "data_models": [\n'
        '    {"name": "User", "table_name": "users", "fields": ["id", "email", "hashed_password"]}\n'
        "  ],\n"
        '  "tech_stack": {"backend": "FastAPI", "database": "PostgreSQL", "frontend": "React"},\n'
        '  "deployment_notes": "Docker + docker-compose",\n'
        '  "scalability_notes": "Stateless API, horizontal scaling",\n'
        '  "out_of_scope": [],\n'
        '  "anything_unclear": ""\n'
        "}\n"
        "status_codes MUST be a plain string like '200 OK, 404 Not Found' — NOT a list or dict.\n"
        "modules[].files MUST be a list of file paths — never empty.\n"
        "All fields are required. Do not add extra nesting."
    )

    def __init__(self, prompt_builder: ArchitectPromptBuilder | None = None) -> None:
        """Wire the Architect prompt builder this action uses."""
        super().__init__(prompt_builder or ArchitectPromptBuilder())

    def run(self, context: object, llm: object):
        """Run architecture generation with a simplified re-prompt fallback.

        On the first attempt, uses the full schema prompt.  If the result has
        empty api_endpoints (indicating a schema parse failure that produced the
        synthesized-modules fallback), makes a second attempt with a simplified
        flat schema that avoids nested objects — the most common parse failure
        cause on qwen3/Bedrock.
        """
        from .base_action import ActionOutput
        import time

        result = super().run(context, llm)

        # Check whether the primary attempt produced real API endpoints
        api_endpoints = (result.structured or {}).get("api_endpoints") or []
        modules = (result.structured or {}).get("modules") or []
        if api_endpoints or len(modules) >= 3:
            # Good enough — primary response was usable
            return result

        logger.warning(
            "WriteArchitecture: primary response has empty api_endpoints (%d modules). "
            "Retrying with simplified schema.",
            len(modules),
        )

        # Re-prompt with simplified schema
        content = getattr(context, "content", "") if context is not None else ""
        project_id = getattr(context, "project_id", "") if context is not None else ""
        prompt = self.prompt_builder.build(content)

        started = time.time()
        response = llm.generate_text(
            prompt,
            system_prompt=self._SIMPLIFIED_SYSTEM_PROMPT,
            stage=self.name,
            agent=self.name,
            project_id=project_id,
            json_mode=self.output_json,
        )
        elapsed_ms = (time.time() - started) * 1000

        # Parse the simplified response — coerce status_codes string → dict
        retry_structured = self._parse_simplified_response(response.content)
        if not retry_structured:
            logger.warning(
                "WriteArchitecture: simplified re-prompt also failed to parse — keeping primary result"
            )
            return result

        retry_api = retry_structured.get("api_endpoints") or []
        retry_modules = retry_structured.get("modules") or []
        if retry_api or len(retry_modules) >= len(modules):
            logger.info(
                "WriteArchitecture: simplified re-prompt succeeded — %d endpoints, %d modules",
                len(retry_api), len(retry_modules),
            )
            tokens = self._extract_tokens(response)
            latency = self._extract_latency_ms(response, elapsed_ms)
            return ActionOutput(
                content=response.content,
                structured=retry_structured,
                tokens_used=(result.tokens_used or 0) + tokens,
                latency_ms=(result.latency_ms or 0.0) + latency,
            )

        return result  # simplified result was no better — keep primary

    def _parse_simplified_response(self, text: str) -> dict[str, Any]:
        """Parse the simplified re-prompt response.

        Coerces status_codes from a plain string ("200 OK, 401 Unauthorized")
        to the dict[str, str] form the schema expects, then runs the standard
        fallback chain.
        """
        from .base_action import BaseAction
        raw = BaseAction.extract_json(text)
        if not raw:
            return {}

        # Coerce simplified status_codes string → dict[str, str]
        for ep in (raw.get("api_endpoints") or []) + (raw.get("api_design") or []):
            if not isinstance(ep, dict):
                continue
            sc = ep.get("status_codes")
            if isinstance(sc, str):
                # "200 OK, 401 Unauthorized" → {"200": "OK", "401": "Unauthorized"}
                codes: dict[str, str] = {}
                for part in sc.split(","):
                    part = part.strip()
                    if part:
                        tokens_split = part.split(None, 1)
                        code = tokens_split[0].strip()
                        desc = tokens_split[1].strip() if len(tokens_split) > 1 else ""
                        codes[code] = desc
                ep["status_codes"] = codes
            elif isinstance(sc, list):
                ep["status_codes"] = {str(code): "" for code in sc}

        try:
            return ArchitectureArtifact.model_validate(raw).model_dump(mode="json")
        except Exception:
            return self._build_fallback_artifact(text)

    def _parse_structured(self, text: str) -> dict[str, Any]:
        """Parse LLM response into ArchitectureArtifact schema.

        On JSON parse / schema-validation failure, builds a fallback artifact
        from the raw text rather than raising — the same graceful-degradation
        pattern used by WriteRequirementsAction.  On empty architecture
        (no modules, endpoints, or data models), synthesises minimal modules
        from implementation_approach / layers so downstream stages always
        receive something concrete to build on.
        """
        parsed = super()._parse_structured(text)
        if not parsed:
            # super() returns {} when model_validate raises (common cause:
            # tech_stack returned as dict[str, dict] instead of dict[str, str],
            # or modules/data_models items have extra/renamed keys).
            logger.warning(
                "WriteArchitecture: LLM output did not match ArchitectureArtifact schema. "
                "Building fallback from raw text. First 300 chars: %s",
                (text or "")[:300],
            )
            parsed = self._build_fallback_artifact(text)

        # Normalize api_design alias → api_endpoints.
        # Some models (e.g. qwen3 on Bedrock) emit "api_design" instead of
        # "api_endpoints". Copy it so every downstream consumer sees the
        # canonical key (reviewer, context_extractor, backend_builder).
        if not parsed.get("api_endpoints") and parsed.get("api_design"):
            parsed["api_endpoints"] = parsed.pop("api_design")

        modules = parsed.get("modules") or []
        api_endpoints = parsed.get("api_endpoints") or []
        data_models = parsed.get("data_models") or []
        if not modules and not api_endpoints and not data_models:
            # The model produced valid JSON but put everything in out_of_scope or
            # simply omitted the design arrays.  Synthesise minimal modules from
            # whatever narrative content it did produce rather than hard-failing.
            logger.warning(
                "WriteArchitecture: empty architecture (no modules, endpoints, or data_models). "
                "out_of_scope=%s. Synthesising modules from implementation_approach/layers.",
                parsed.get("out_of_scope", []),
            )
            parsed["modules"] = self._synthesize_modules_from_approach(parsed)

        return parsed

    # ── Fallback artifact construction ────────────────────────────────────────

    @classmethod
    def _build_fallback_artifact(cls, raw_text: str) -> dict[str, Any]:
        """Build a minimal ArchitectureArtifact dict from raw LLM text.

        Called when the base schema validation fails.  Extracts whatever the
        model produced, coerces known problem fields (tech_stack nested dicts,
        oversized field values), then attempts model_validate() again.  If that
        still fails, falls back to a safe hand-crafted dict.
        """
        raw = cls.extract_json(raw_text)

        # ── Coerce tech_stack: dict[str, Any] → dict[str, str] ──────────────
        # Qwen3 commonly returns {"frontend": {"framework": "React", "build": "Vite"}}
        # instead of {"frontend": "React (Vite)"}.  Flatten to string values.
        tech_stack = raw.get("tech_stack") or {}
        if isinstance(tech_stack, dict):
            coerced: dict[str, str] = {}
            for layer, value in tech_stack.items():
                if isinstance(value, str):
                    coerced[str(layer)] = value
                elif isinstance(value, dict):
                    coerced[str(layer)] = ", ".join(str(v) for v in value.values() if v)[:200]
                else:
                    coerced[str(layer)] = str(value)[:200]
            raw["tech_stack"] = coerced

        # ── Coerce list fields: filter nulls, ensure items are dicts ─────────
        # LLMs occasionally emit null entries in arrays or wrap list items in
        # an extra layer (e.g. {"modules": [null, {"name": "Auth"}, ...]} or
        # status_codes with integer keys).  Strip non-dict entries so Pydantic
        # can validate ModuleSpec / APIEndpoint / DataModel without raising.
        for list_key in ("modules", "api_endpoints", "api_design", "data_models"):
            raw_list = raw.get(list_key)
            if isinstance(raw_list, list):
                raw[list_key] = [item for item in raw_list if isinstance(item, dict)]

        # Coerce layers / out_of_scope: must be list[str]
        for str_list_key in ("layers", "out_of_scope"):
            raw_val = raw.get(str_list_key)
            if isinstance(raw_val, list):
                raw[str_list_key] = [str(v) for v in raw_val if v is not None]
            elif raw_val is not None:
                raw[str_list_key] = []

        # Coerce status_codes on each APIEndpoint: LLM may emit a list[int]
        # ([200, 401, 400]) or a dict with int keys ({200: "OK"}).  Normalise
        # to dict[str, str] in all cases so Pydantic accepts the value.
        # NOTE: the original expression had an operator-precedence bug —
        # `api_endpoints or [] + api_design` was parsed as
        # `api_endpoints or ([] + api_design)`.  Explicit list concatenation below.
        _all_eps = list(raw.get("api_endpoints") or []) + list(raw.get("api_design") or [])
        for ep in _all_eps:
            if not isinstance(ep, dict):
                continue
            sc = ep.get("status_codes")
            if isinstance(sc, dict):
                ep["status_codes"] = {str(k): str(v) for k, v in sc.items()}
            elif isinstance(sc, list):
                # LLM returned [200, 401, 400] — convert to {"200": "", "401": "", ...}
                ep["status_codes"] = {str(code): "" for code in sc if code is not None}

        # ── Re-attempt schema validation with coerced fields ─────────────────
        try:
            return ArchitectureArtifact.model_validate(raw).model_dump(mode="json")
        except Exception as _coerce_exc:
            logger.warning(
                "WriteArchitecture: coerced fallback model_validate still failed (%s) — "
                "building minimal hand-crafted artifact. raw keys=%s",
                _coerce_exc,
                list(raw.keys()),
            )

        # ── Extract narrative fields from raw JSON or raw text ───────────────
        implementation_approach: str = (
            raw.get("implementation_approach")
            or raw.get("approach")
            or cls._extract_field_from_text(raw_text, "implementation_approach")
            or raw_text[:500].strip()
        )
        layers: list[str] = raw.get("layers") or []
        if not isinstance(layers, list):
            layers = []
        layers = [str(l) for l in layers[:10]]

        artifact = ArchitectureArtifact(
            implementation_approach=implementation_approach,
            approach=raw.get("approach") or "",
            layers=layers,
            tech_stack=raw.get("tech_stack") or {},
            deployment_notes=raw.get("deployment_notes") or "",
            scalability_notes=raw.get("scalability_notes") or "",
            anything_unclear=(
                "Architecture could not be fully parsed from LLM output — "
                "raw response was partially extracted."
            ),
        )
        return artifact.model_dump(mode="json")

    @staticmethod
    def _extract_field_from_text(text: str, field: str) -> str:
        """Regex-extract a JSON string field value from raw LLM output."""
        m = re.search(rf'"{re.escape(field)}"\s*:\s*"([^"{{}}]{{1,500}})"', text or "")
        return m.group(1) if m else ""

    # ── Module synthesis ──────────────────────────────────────────────────────

    @staticmethod
    def _synthesize_modules_from_approach(parsed: dict[str, Any]) -> list[dict[str, Any]]:
        """Build minimal ModuleSpec dicts from implementation_approach and layers.

        Called when all architecture arrays are empty.  Creates at least one
        module per layer so the reviewer's critical check passes and downstream
        stages (BackendDev, FrontendDev) have a concrete skeleton to build on.
        """
        approach: str = (
            parsed.get("implementation_approach")
            or parsed.get("approach")
            or ""
        )
        layers: list[str] = parsed.get("layers") or []
        tech_stack: dict[str, str] = parsed.get("tech_stack") or {}

        # Derive layers from approach text if none were specified
        if not layers:
            layer_keywords = [
                "frontend", "backend", "database", "api", "auth",
                "service", "ui", "data", "cache", "queue",
            ]
            layers = [
                kw.title()
                for kw in layer_keywords
                if kw.lower() in approach.lower()
            ][:6]
        if not layers:
            layers = ["Core"]

        # Map layer keywords to conventional module names and file paths so that
        # WriteFilePlan's fallback produces idiomatic names (main.py, models.py…)
        # instead of generic blobs like businessmodule.py / frontendmodule.py.
        _LAYER_TO_MODULE: dict[str, tuple[str, list[str]]] = {
            "frontend":       ("Frontend",  ["src/App.jsx", "src/index.jsx"]),
            "backend":        ("Backend",   ["app/main.py", "app/routes.py"]),
            "api":            ("API",       ["app/routes.py", "app/schemas.py"]),
            "database":       ("Database",  ["app/models/models.py", "app/db.py"]),
            "data":           ("Data",      ["app/models/models.py"]),
            "auth":           ("Auth",      ["app/auth.py"]),
            "service":        ("Service",   ["app/service.py"]),
            "ui":             ("UI",        ["src/components/App.jsx"]),
            "cache":          ("Cache",     ["app/cache.py"]),
            "queue":          ("Queue",     ["app/queue.py"]),
            "core":           ("Core",      ["app/main.py"]),
        }

        modules: list[dict[str, Any]] = []
        for layer in layers[:8]:
            tech = (
                tech_stack.get(layer.lower())
                or tech_stack.get(layer)
                or tech_stack.get(layer.title())
                or ""
            )
            name, files = _LAYER_TO_MODULE.get(layer.lower(), (f"{layer.title()}", []))
            modules.append({
                "name": name,
                "purpose": f"{layer} layer — {approach[:120]}",
                "layer": layer,
                "technology": tech,
                "dependencies": [],
                "exports": [],
                "files": files,
            })
        logger.warning(
            "WriteArchitecture: synthesised %d module(s) from layers/approach.",
            len(modules),
        )
        return modules
