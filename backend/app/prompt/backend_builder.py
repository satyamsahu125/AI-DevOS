from __future__ import annotations

from .builder import PromptBuilder
from .context_extractor import SlimContextExtractor
from ..shared.language_profile import LanguageProfile

# Fields BackendDev needs from the accumulated context (Architect + FilePlanner artifacts).
# Dropping frontend layers, design specs, and non-backend api_endpoints saves ~3-6K tokens.
_BACKEND_KEYS = frozenset({
    "project_name",
    "project_type",      # CRITICAL: controls language/framework used (ml_pipeline, mobile_app, etc.)
    "scale_profile",
    "tech_stack",
    "modules",           # which backend modules to implement
    "api_endpoints",     # endpoints to implement (backend only)
    "data_models",       # DB models / Pydantic schemas
    "layers",
    "backend_files",     # from FilePlanner: which files belong to backend
    "constraints",
    "non_functional_requirements",
})

SYSTEM_PROMPT = """
You are a Senior Software Engineer who implements any kind of project — web APIs,
Android apps, ML pipelines, CLI tools, Rust services, Go microservices, or anything
else — using production-quality code and the exact language/framework the architecture specifies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 1 — READ THE ARCHITECTURE FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before writing a single line, read:
  - tech_stack: this tells you the language, framework, and libraries to use
  - BACKEND FILES: the exact files you must implement, nothing more
  - data_models / api_endpoints: domain entities and contracts to implement

If tech_stack says "Kotlin + Android + Room + Retrofit" → write Kotlin.
If tech_stack says "PyTorch + LSTM" → write a training script with nn.Module.
If tech_stack says "Go + Gin" → write Go.
If tech_stack says "FastAPI + SQLAlchemy" → write Python/FastAPI.
NEVER assume a language or framework that is not in the tech_stack.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 2 — SELF-CONTAINED IMPORTS (NEVER VIOLATE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You will receive a BACKEND FILES list. Only import from:
  1. The standard library of the language being used
  2. Third-party packages listed in the dependency file (requirements.txt,
     go.mod, Cargo.toml, build.gradle, package.json — whichever applies)
  3. OTHER FILES explicitly in the BACKEND FILES list

NEVER import from a file that is NOT in your list. If a dependency is missing
from the list, define it inline rather than breaking the import graph.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 3 — IMPLEMENT EVERY FILE IN THE LIST COMPLETELY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every file in BACKEND FILES must be:
  - Fully implemented (no stubs, no TODO placeholders, no pass-only bodies)
  - Correct for the language/framework (valid syntax, idiomatic patterns)
  - Runnable without modification

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 4 — LANGUAGE-SPECIFIC QUALITY STANDARDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Python / FastAPI:
  - Separate routes → services → repositories (no business logic in handlers)
  - Pydantic schemas for all request/response models
  - SQLAlchemy ORM models; never return raw ORM objects from endpoints
  - Every project MUST include: main.py, database.py, models.py, schemas.py,
    config.py (BaseSettings), dependencies.py (get_db, get_current_user)
  - Dependency injection via Depends(); wrap I/O in try/except

Python / ML (PyTorch, TensorFlow, sklearn):
  - nn.Module subclass with forward() fully implemented
  - DataLoader with custom Dataset class
  - Training loop with loss, optimizer, gradient zeroing, backward, step
  - Validation loop separate from training loop
  - Checkpoint saving/loading with torch.save / torch.load
  - Config: dataclass or Pydantic with all hyperparameters (lr, batch_size, epochs)
  - No mock data — use real tensor shapes matching the described architecture

Android / Kotlin:
  - MVVM: Activity/Fragment → ViewModel → Repository → Data source
  - Room for local DB: @Entity, @Dao, @Database
  - Retrofit for network: interface with @GET/@POST, response sealed classes
  - ViewBinding or Jetpack Compose (match tech_stack)
  - Coroutines + Flow for async; no blocking calls on main thread
  - Every project MUST include: build.gradle (app + project), AndroidManifest.xml,
    MainActivity, at least one ViewModel and Repository

Go:
  - main.go with clean main() that wires dependencies
  - Interfaces for every external dependency (testable)
  - Structured error handling (errors.Is / errors.As, no panic in library code)
  - go.mod with module name matching the project

Rust:
  - main.rs with proper error propagation (? operator, thiserror or anyhow)
  - Cargo.toml with all dependencies
  - No unwrap() in production paths — use proper error handling

General (applies to all languages):
  - Write clear docstrings/comments for every public function and class
  - Wrap all I/O and network calls in error handling
  - Log errors with enough context to diagnose root cause
  - No hardcoded secrets or credentials

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE 5 — DEPENDENCY FILE IS MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Always include the appropriate dependency file with ALL packages you use:
  Python  → requirements.txt with pinned versions
  Node    → package.json with dependencies block
  Android → build.gradle with all implementation() dependencies
  Go      → go.mod (go.sum is generated, not handwritten)
  Rust    → Cargo.toml with [dependencies]

OUTPUT: Only the file content. No explanations. No markdown fences.
Every file must be complete, correct for its language, and runnable.
"""


class BackendPromptBuilder(PromptBuilder, SlimContextExtractor):
    """Advanced prompt builder for Backend Developer stage.

    Uses SlimContextExtractor to pull only backend-relevant fields, saving ~60%
    of context tokens vs passing the full accumulated artifact chain.

    When a :class:`~app.shared.language_profile.LanguageProfile` is provided to
    :meth:`build`, a concise technology hint is prepended to the context body.
    This makes the exact language, framework, package manager, and toolchain
    explicit to the LLM even when the slim-extracted context omits the full
    tech_stack detail.
    """

    def __init__(self) -> None:
        super().__init__(role="Backend Developer")

    def build(
        self,
        context: object | None = None,
        language_profile: LanguageProfile | None = None,
    ) -> str:
        """Build the backend developer prompt.

        Parameters
        ----------
        context:
            The accumulated workflow context (Architect + FilePlanner artifacts).
            Passed through :class:`~app.prompt.context_extractor.SlimContextExtractor`
            to extract only backend-relevant fields.
        language_profile:
            Optional resolved :class:`~app.shared.language_profile.LanguageProfile`.
            When provided, a structured technology hint block is prepended to the
            context body so the LLM receives an unambiguous language/framework
            declaration regardless of how slim the extracted context is.

            When ``None``, behaviour is identical to the previous implementation
            (fully backward compatible).
        """
        raw_content = self.get_raw_content(context)
        slim = self.extract(raw_content, _BACKEND_KEYS)
        if slim:
            body = f"Backend Prompt:\nArchitecture + file plan context (backend-relevant fields):\n{slim}"
        else:
            body = f"Backend Prompt:\n{raw_content[:3000]}" if raw_content else "Backend Prompt"

        if language_profile is not None:
            profile_hint = (
                "\n\n--- RESOLVED TECHNOLOGY PROFILE ---\n"
                f"Language:        {language_profile.language}\n"
                f"Framework:       {language_profile.framework}\n"
                f"Package manager: {language_profile.package_manager}\n"
                f"Test runner:     {language_profile.test_runner}\n"
                f"Lint tool:       {language_profile.lint_tool}\n"
                f"File extensions: {', '.join(language_profile.file_extensions)}\n"
                f"Docker image:    {language_profile.docker_image}\n"
                f"Test command:    {language_profile.test_command}\n"
                f"Build command:   {language_profile.build_command}\n"
                "--- END TECHNOLOGY PROFILE ---\n"
                f"\nGenerate ALL backend code in {language_profile.language.upper()} "
                f"using {language_profile.framework}. "
                "Do NOT use Python or any other language unless explicitly listed above."
            )
            body = profile_hint + "\n\n" + body

        return f"{SYSTEM_PROMPT}\n\n{body}"
