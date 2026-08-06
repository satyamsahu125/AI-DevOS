# Phase R6 — Integration Agent

**Timeline:** Week 7–9  
**Depends on:** R2 (verification catches broken imports) + R5 (live preview shows integrations working)  
**Problem:** Generated apps have no connection to external services. Authentication is stubbed, payments are commented out, email is a TODO. The generated app is a prototype, not a product.  
**Outcome:** A new Integration stage maps external service requirements from the architecture artifact and generates client code, environment variable stubs, and setup instructions for each service.

---

## Why This Matters

This is the single largest functional gap between AI DevOS and Emergent for real-world use cases. Nearly every commercial app needs at least one external service: user authentication, payments, file storage, or email. Emergent's Integration Agent + Playbooks handle this automatically. AI DevOS generates apps that reference services but never connects them.

---

## New Stage: Integration

**Position in pipeline:** After `FrontendDeveloper`, before `QA`

**New enum value:** Add `Integration` to `backend/app/shared/enums/stage.py`

**New agent:** `backend/app/agents/integration_developer.py`

---

## Playbook Library

**File:** `backend/app/integration/playbooks/`

A Playbook is a JSON manifest describing how to integrate a specific service:

```json
{
  "service": "stripe",
  "display_name": "Stripe Payments",
  "trigger_keywords": ["payment", "billing", "subscription", "checkout", "invoice", "purchase"],
  "env_vars": [
    {"name": "STRIPE_SECRET_KEY", "description": "Stripe secret key from dashboard", "example": "sk_live_..."},
    {"name": "STRIPE_PUBLISHABLE_KEY", "description": "Stripe publishable key", "example": "pk_live_..."},
    {"name": "STRIPE_WEBHOOK_SECRET", "description": "Stripe webhook signing secret", "example": "whsec_..."}
  ],
  "packages": {"python": "stripe==7.0.0", "node": "stripe@14.0.0"},
  "files_to_generate": [
    {
      "path": "services/stripe_client.py",
      "description": "Stripe client with charge, subscription, webhook verification",
      "template_hint": "Use stripe.PaymentIntent.create() for one-time payments, stripe.Subscription.create() for recurring"
    }
  ],
  "setup_instructions": "1. Create account at stripe.com\n2. Copy keys from Dashboard → Developers → API Keys\n3. Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY in .env"
}
```

**Initial playbook set (implement first):**
- `stripe.json` — payments
- `jwt_auth.json` — JWT authentication (python-jose + passlib)
- `google_oauth.json` — Google OAuth login
- `aws_s3.json` — file storage
- `sendgrid.json` — transactional email
- `posthog.json` — product analytics

---

## Integration Agent Logic

```python
class IntegrationDeveloper:
    """Reads architecture artifact, detects required services, generates integration code."""

    def __init__(self, llm, write_files_action, playbook_dir: Path) -> None:
        self._llm = llm
        self._write = write_files_action
        self._playbooks = self._load_playbooks(playbook_dir)

    def analyse(self, architecture_artifact: dict) -> list[str]:
        """Return list of service names detected in architecture artifact."""
        arch_text = json.dumps(architecture_artifact).lower()
        detected = []
        for playbook in self._playbooks.values():
            if any(kw in arch_text for kw in playbook["trigger_keywords"]):
                detected.append(playbook["service"])
        return detected

    def integrate(self, project_id: str, detected_services: list[str], 
                  project_dir: Path, stack: str) -> IntegrationResult:
        """Generate integration code for each detected service."""
        results = []
        for service_name in detected_services:
            playbook = self._playbooks[service_name]
            for file_spec in playbook["files_to_generate"]:
                content = self._generate_file(playbook, file_spec, stack)
                self._write.write_single(project_dir / file_spec["path"], content)
                results.append(file_spec["path"])
        return IntegrationResult(service_names=detected_services, files_written=results)
```

---

## API: Configure Integrations

### GET /projects/{id}/integrations
Returns detected integrations and their configuration status:
```json
{
  "integrations": [
    {
      "service": "stripe",
      "display_name": "Stripe Payments",
      "status": "configured" | "pending_env_vars",
      "env_vars": [
        {"name": "STRIPE_SECRET_KEY", "configured": false, "description": "..."}
      ],
      "files_generated": ["services/stripe_client.py"]
    }
  ]
}
```

### POST /projects/{id}/integrations/{service}/configure
Body: `{"env_vars": {"STRIPE_SECRET_KEY": "sk_live_...", ...}}`

Writes env vars to the project's `.env` file (not the server's `.env`). Returns 204.

**Security:** Env var values are written to `{project_workspace}/.env` only. Never logged. Never stored in the main database.

---

## RUN_INSTRUCTIONS.md Update

After Integration stage completes, append a "Required Environment Variables" section to `RUN_INSTRUCTIONS.md`:

```markdown
## Required Environment Variables

Before running the app, set these environment variables in your `.env` file:

### Stripe Payments
- `STRIPE_SECRET_KEY` — Stripe secret key from Dashboard → API Keys
- `STRIPE_PUBLISHABLE_KEY` — Stripe publishable key
- [Full setup: https://stripe.com/docs/keys]

### Authentication (JWT)
- `JWT_SECRET_KEY` — Any random 32-character string: `openssl rand -hex 32`
- `JWT_ALGORITHM` — Set to: `HS256`
```

---

## Exit Criteria

- [ ] An architecture artifact containing "payment" triggers Stripe integration detection
- [ ] `services/stripe_client.py` is generated and passes R2 syntax check (no import errors)
- [ ] `GET /projects/{id}/integrations` returns correct detected services
- [ ] `POST /projects/{id}/integrations/stripe/configure` writes vars to project `.env` only (not server `.env`)
- [ ] `RUN_INSTRUCTIONS.md` contains "Required Environment Variables" section with setup links
- [ ] All R1–R5 exit criteria still passing
