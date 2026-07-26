#!/usr/bin/env python3
"""End-to-end test: Bus Booking Platform — all agents, logged and verified.

Runs every AI DevOS agent against a realistic bus booking scenario,
logging inputs, outputs, timings, and structured data for each stage.
Prints a colour-coded summary table at the end.

Usage:
    cd backend
    python tests/e2e_bus_booking.py
    python tests/e2e_bus_booking.py --verbose   # show full artifact content

Architecture constraints respected:
  - Stateless agents — no shared mutable state between runs
  - Stub LLM — no live Ollama/Bedrock needed; each stage gets
    domain-specific canned JSON so schema validation passes
  - No file system writes — ProjectWriter and FileValidator mocked
  - Pipeline order matches DependencyGraph.STAGE_ORDER
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("app.execution.safety_policy", MagicMock())

from app.llm.response import LLMResponse
from app.shared.models.stage_artifact import StageArtifact

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def _ok(s):   return f"{GREEN}✓ {s}{RESET}"
def _fail(s): return f"{RED}✗ {s}{RESET}"
def _warn(s): return f"{YELLOW}⚠ {s}{RESET}"
def _hdr(s):  return f"{BOLD}{CYAN}{s}{RESET}"


# ===========================================================================
# Canned LLM responses — bus booking domain, one per stage
# ===========================================================================

BUS_BOOKING_CANNED: dict[str, str] = {

    "domain_research": json.dumps({
        "domain": "transportation / bus booking",
        "complexity": "high",
        "standard_modules": [
            "Route Management", "Seat Inventory", "Booking Engine",
            "Payment Gateway", "Notification Service", "Cancellation & Refund"
        ],
        "standard_actors": ["Passenger", "Bus Operator", "Admin", "Payment Provider"],
        "standard_integrations": ["Razorpay", "Twilio SMS", "Google Maps Routes API"],
        "questions_to_ask": [
            "Do operators set their own seat prices or is pricing centralised?",
            "Which payment methods must be supported at launch?",
            "Is partial cancellation (specific seats) required?"
        ],
        "questions_not_to_ask": [
            "What is a bus?",
            "Why do people travel?"
        ],
        "common_pitfalls": [
            "Race conditions on last available seat",
            "Payment gateway timeout handling",
            "Timezone alignment for departure schedules"
        ],
        "regulatory_concerns": [
            "PCI-DSS compliance for card payments",
            "Passenger data GDPR obligations"
        ],
        "comparable_products": ["RedBus", "Busbud", "FlixBus"],
        "anything_unusual": ""
    }),

    "strategic_review": json.dumps({
        "strategic_brief": "Build a Bus Booking Platform that connects passengers with "
                           "bus operators. Core value: frictionless route discovery, "
                           "real-time seat selection, and instant booking confirmation.",
        "target_users": ["Urban commuters", "Inter-city travellers"],
        "success_metrics": ["Booking conversion > 60%", "Payment success > 95%", "p99 seat lock < 200ms"],
        "risks": ["Inventory race conditions", "Payment gateway SLA"],
        "recommended_mvp_scope": ["Route search", "Seat selection", "UPI/card payment", "E-ticket delivery"],
        "out_of_scope": ["Loyalty programme", "Multi-modal trips", "Operator fleet management"]
    }),

    "product_owner": json.dumps({
        "title": "Bus Booking Platform — Product Requirements",
        "overview": "A web platform where passengers search routes, pick seats, pay, and receive e-tickets.",
        "user_stories": [
            "As a passenger I can search routes by origin, destination and date",
            "As a passenger I can view seat map and select seats",
            "As a passenger I can pay via UPI or credit card",
            "As a passenger I can download my e-ticket as PDF",
            "As a passenger I can cancel a booking and receive a refund"
        ],
        "functional_requirements": [
            "Route search with filter by operator, departure time, bus type",
            "Real-time seat availability with optimistic locking",
            "Payment integration: Razorpay (UPI, card, netbanking)",
            "E-ticket generation (PDF with QR code)",
            "Cancellation with configurable refund policy"
        ],
        "non_functional_requirements": {
            "performance": "Seat availability API < 200ms p99",
            "reliability": "99.9% uptime SLA",
            "security": "PCI-DSS SAQ-A compliant; no raw card data stored"
        },
        "out_of_scope": ["Loyalty programme", "Fleet management", "Multi-modal journeys"]
    }),

    "architect": json.dumps({
        "implementation_approach": "Layered REST API with FastAPI, PostgreSQL, Redis for seat locking",
        "approach": "REST",
        "layers": ["api", "service", "repository", "infrastructure"],
        "modules": [
            {"name": "RouteService", "purpose": "Route search and schedule management",
             "layer": "service", "technology": "FastAPI", "dependencies": [], "exports": ["search_routes"], "files": []},
            {"name": "BookingService", "purpose": "Seat reservation with optimistic locking",
             "layer": "service", "technology": "FastAPI + Redis", "dependencies": ["RouteService"], "exports": ["reserve_seat", "confirm_booking"], "files": []},
            {"name": "PaymentService", "purpose": "Razorpay payment orchestration",
             "layer": "service", "technology": "FastAPI + Razorpay SDK", "dependencies": ["BookingService"], "exports": ["initiate_payment", "verify_payment"], "files": []},
            {"name": "NotificationService", "purpose": "E-ticket delivery via email/SMS",
             "layer": "service", "technology": "Celery + Twilio", "dependencies": ["BookingService"], "exports": ["send_ticket"], "files": []}
        ],
        "api_endpoints": [
            {"path": "/api/routes/search", "method": "GET", "description": "Search available routes",
             "request_body": {}, "response_schema": {"routes": "list"}, "auth_required": False, "status_codes": [200, 400]},
            {"path": "/api/bookings", "method": "POST", "description": "Create booking",
             "request_body": {"route_id": "str", "seat_ids": "list", "passenger": "dict"},
             "response_schema": {"booking_id": "str", "status": "str"}, "auth_required": True, "status_codes": [201, 409, 422]},
            {"path": "/api/payments/initiate", "method": "POST", "description": "Initiate payment",
             "request_body": {"booking_id": "str", "method": "str"},
             "response_schema": {"payment_url": "str"}, "auth_required": True, "status_codes": [200, 402]}
        ],
        "api_design": [],
        "data_models": [
            {"name": "Route", "table_name": "routes",
             "fields": [{"name": "id", "type": "UUID"}, {"name": "origin", "type": "str"}, {"name": "destination", "type": "str"}, {"name": "departure_at", "type": "datetime"}],
             "relationships": ["has_many Buses", "has_many Bookings"], "indexes": ["origin,destination", "departure_at"]},
            {"name": "Booking", "table_name": "bookings",
             "fields": [{"name": "id", "type": "UUID"}, {"name": "route_id", "type": "UUID"}, {"name": "seat_ids", "type": "list[UUID]"}, {"name": "status", "type": "enum"}, {"name": "amount_paid", "type": "Decimal"}],
             "relationships": ["belongs_to Route", "belongs_to User"], "indexes": ["route_id", "status"]}
        ],
        "tech_stack": {"backend": "FastAPI 0.115", "database": "PostgreSQL 16", "cache": "Redis 7", "queue": "Celery + RabbitMQ", "frontend": "React 18 + Vite"},
        "deployment_notes": "Docker Compose for local; Kubernetes on AWS EKS for production",
        "scalability_notes": "Redis seat lock TTL=5min; horizontal API scaling; DB read replicas for route search",
        "out_of_scope": ["Loyalty programme", "Fleet management"],
        "anything_unclear": ""
    }),

    "designer": json.dumps({
        "design_system": "Material Design 3 with brand-primary #1A73E8",
        "pages": [
            {"name": "Search Page", "route": "/", "purpose": "Route search with origin/destination/date pickers"},
            {"name": "Results Page", "route": "/routes", "purpose": "Filterable list of available buses"},
            {"name": "Seat Map Page", "route": "/select-seats", "purpose": "Interactive seat grid with colour coding"},
            {"name": "Checkout Page", "route": "/checkout", "purpose": "Passenger details + payment method selection"},
            {"name": "Confirmation Page", "route": "/booking/:id", "purpose": "E-ticket with QR code and download link"}
        ],
        "components": [
            "SearchBar", "RouteCard", "SeatGrid", "SeatLegend",
            "PassengerForm", "PaymentMethodSelector", "BookingConfirmationCard"
        ],
        "accessibility": "WCAG 2.1 AA — all interactive elements keyboard-navigable",
        "responsive": "Mobile-first; breakpoints 375/768/1280px",
        "colour_palette": {"primary": "#1A73E8", "success": "#34A853", "error": "#EA4335", "warning": "#FBBC05"}
    }),

    "security": json.dumps({
        "security_summary": "Bus Booking Platform passes baseline security review with two critical remediations required.",
        "threat_model": [
            "Race condition on seat reservation — mitigated by Redis distributed lock",
            "Payment replay attack — mitigated by idempotency keys on Razorpay",
            "PII data leak — passenger name/phone encrypted at rest (AES-256)"
        ],
        "critical_issues": [
            "Raw payment instrument must NEVER reach our servers — enforce Razorpay.js client-side tokenisation",
            "JWT secret must be rotated quarterly and stored in AWS Secrets Manager"
        ],
        "recommendations": [
            "Add rate limiting on /api/routes/search (100 req/min per IP)",
            "Enable SQL query parameterisation everywhere — ORM enforces this with SQLAlchemy",
            "Log booking cancellations to immutable audit trail"
        ],
        "compliance": ["PCI-DSS SAQ-A", "GDPR Article 17 (right to erasure) implemented via soft-delete"]
    }),

    "sprint_planner": json.dumps({
        "total_sprints": 3,
        "sprints": [
            {
                "sprint_number": 1,
                "name": "Core Backend — Routes & Booking",
                "goal": "Ship route search API, seat inventory model, and booking creation endpoint",
                "features": ["Route CRUD", "Seat model", "POST /api/bookings"],
                "duration_days": 14,
                "estimated_story_points": 40
            },
            {
                "sprint_number": 2,
                "name": "Payment & Notifications",
                "goal": "Integrate Razorpay, generate e-tickets, send SMS confirmations",
                "features": ["Razorpay integration", "PDF e-ticket", "Twilio SMS"],
                "duration_days": 14,
                "estimated_story_points": 35
            },
            {
                "sprint_number": 3,
                "name": "Frontend & Polish",
                "goal": "Build React UI: search, seat map, checkout, confirmation",
                "features": ["SearchPage", "SeatGrid", "CheckoutFlow", "BookingConfirmation"],
                "duration_days": 14,
                "estimated_story_points": 45
            }
        ]
    }),

    "scrum_master": json.dumps({
        "sprint_goal": "Deliver core route search and booking API for Sprint 1",
        "ceremonies": {
            "daily_standup": "09:00 IST — async via Slack thread",
            "sprint_planning": "Monday 10:00 IST (2h)",
            "sprint_review": "Friday 15:00 IST (1h)",
            "retrospective": "Friday 16:00 IST (45min)"
        },
        "definition_of_done": [
            "Unit tests pass with ≥80% coverage",
            "API documented in OpenAPI 3.1",
            "Code reviewed by at least one peer",
            "Deployed to staging and smoke-tested"
        ],
        "velocity_target": 40,
        "team_size": 3,
        "risks_to_watch": ["Razorpay sandbox delays", "PCI-DSS review timeline"]
    }),

    "file_plan": json.dumps({
        "sprint_number": 1,
        "generation_order": [
            "backend/models/route.py",
            "backend/models/booking.py",
            "backend/services/route_service.py",
            "backend/services/booking_service.py",
            "backend/api/routes.py",
            "backend/api/bookings.py"
        ],
        "files": {
            "backend/models/route.py": {"file_path": "backend/models/route.py", "language": "python", "purpose": "SQLAlchemy Route model"},
            "backend/models/booking.py": {"file_path": "backend/models/booking.py", "language": "python", "purpose": "SQLAlchemy Booking model"},
            "backend/services/route_service.py": {"file_path": "backend/services/route_service.py", "language": "python", "purpose": "Route search business logic"},
            "backend/services/booking_service.py": {"file_path": "backend/services/booking_service.py", "language": "python", "purpose": "Seat reservation with Redis locking"},
            "backend/api/routes.py": {"file_path": "backend/api/routes.py", "language": "python", "purpose": "FastAPI router for /api/routes"},
            "backend/api/bookings.py": {"file_path": "backend/api/bookings.py", "language": "python", "purpose": "FastAPI router for /api/bookings"}
        },
        "tech_stack": {"backend": "FastAPI", "database": "PostgreSQL", "cache": "Redis"}
    }),

    "backend": "class Route(Base):\n    __tablename__ = 'routes'\n    id = Column(UUID, primary_key=True)\n    origin = Column(String(100), nullable=False)\n    destination = Column(String(100), nullable=False)\n    departure_at = Column(DateTime(timezone=True), nullable=False)",

    "frontend": "const SearchPage = () => {\n  const [routes, setRoutes] = React.useState([]);\n  return (\n    <div className='search-page'>\n      <SearchBar onSearch={setRoutes} />\n      {routes.map(r => <RouteCard key={r.id} route={r} />)}\n    </div>\n  );\n};",

    "qa": "import pytest\nfrom fastapi.testclient import TestClient\n\ndef test_search_routes_returns_list(client):\n    resp = client.get('/api/routes/search?origin=Delhi&destination=Agra&date=2026-08-01')\n    assert resp.status_code == 200\n    assert isinstance(resp.json()['routes'], list)\n\ndef test_create_booking_requires_auth(client):\n    resp = client.post('/api/bookings', json={'route_id': 'r1', 'seat_ids': ['s1']})\n    assert resp.status_code == 401",

    "devops": "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nEXPOSE 8000\nCMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]",

    "document": "# Bus Booking Platform\n\n## Overview\nA FastAPI + React platform for searching bus routes and booking seats in real-time.\n\n## Architecture\n- Backend: FastAPI + PostgreSQL + Redis\n- Frontend: React 18 + Vite\n- Payments: Razorpay\n- Notifications: Twilio SMS\n\n## Quick Start\n```bash\ndocker-compose up --build\n```\nVisit http://localhost:3000",

    "retro": json.dumps({
        "sprint_summary": "Sprint 1 delivered all 6 planned backend files on time. Seat locking via Redis proved robust.",
        "what_worked": [
            "Daily standups caught the Razorpay sandbox issue on day 3",
            "SQLAlchemy async mode reduced boilerplate by 40%",
            "Peer review process caught a SQL injection vector before it merged"
        ],
        "what_failed": [
            "Redis TTL was initially set too short (30s) causing false seat conflicts",
            "Missing index on routes.departure_at caused slow queries in staging"
        ],
        "action_items": [
            {"action": "Increase Redis seat lock TTL to 300s", "owner": "Backend team", "due": "Sprint 2 day 1"},
            {"action": "Add composite index (origin, destination, departure_at)", "owner": "DB lead", "due": "Sprint 2 day 2"}
        ],
        "velocity_achieved": 38,
        "velocity_target": 40
    }),

    "clarification": json.dumps({
        "questions": [
            {
                "index": 1,
                "question": "Should passengers be able to select specific seats or only seat category (window/aisle)?",
                "category": "WHAT_IS_IT",
                "priority": "MAJOR"
            },
            {
                "index": 2,
                "question": "Which payment methods must be supported at launch: UPI, credit card, netbanking, wallets?",
                "category": "WHAT_IS_IT",
                "priority": "MAJOR"
            },
            {
                "index": 3,
                "question": "What is the cancellation policy — full refund, partial, or operator-defined?",
                "category": "WHAT_IS_IT",
                "priority": "MINOR"
            }
        ]
    }),
}


# ===========================================================================
# Stage-aware Stub LLM
# ===========================================================================

class _BusBookingLLM:
    """Returns domain-accurate canned responses per stage — no live LLM needed.

    Matching priority:
      1. Explicit `stage` kwarg → key lookup in BUS_BOOKING_CANNED
      2. Keyword scan of system_prompt + prompt → infer stage
      3. Fallback: strategic_review JSON (safe non-JSON-strict fallback)
    """

    # Keyword → canned key, ordered most-specific first
    _KEYWORD_MAP: list[tuple[str, str]] = [
        ("scrum",           "scrum_master"),
        ("standup",         "scrum_master"),
        ("ceremony",        "scrum_master"),
        ("definition of done", "scrum_master"),
        ("question",        "clarification"),
        ("clarif",          "clarification"),
        ("domain research", "domain_research"),
        ("pitfall",         "domain_research"),
        ("architecture",    "architect"),
        ("sprint plan",     "sprint_planner"),
        ("sprint number",   "sprint_planner"),
        ("file plan",       "file_plan"),
        ("retrospective",   "retro"),
        ("security",        "security"),
        ("devops",          "devops"),
        ("dockerfile",      "devops"),
        ("deployment",      "devops"),
        ("readme",          "document"),
        ("documentation",   "document"),
        ("design system",   "designer"),
        ("ui",              "designer"),
        ("requirements",    "product_owner"),
        ("user stories",    "product_owner"),
    ]

    def __init__(self) -> None:
        self.call_log: list[dict] = []

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        stage: str = "",
        **kwargs,
    ) -> LLMResponse:
        # 1. Explicit stage kwarg
        stage_key = (stage or "").lower().replace(" ", "_").replace("-", "_")
        content = BUS_BOOKING_CANNED.get(stage_key)

        # 2. Keyword scan when stage is empty or unrecognised
        if not content:
            combined = (system_prompt + " " + prompt).lower()
            for keyword, key in self._KEYWORD_MAP:
                if keyword in combined:
                    content = BUS_BOOKING_CANNED.get(key)
                    stage_key = key
                    break

        # 3. Generic fallback
        if not content:
            content = BUS_BOOKING_CANNED.get("strategic_review")

        self.call_log.append({"stage": stage_key, "prompt_len": len(prompt), "response_len": len(content)})
        return LLMResponse(
            content=content, model="bus-booking-stub",
            finish_reason="stop", input_tokens=0, output_tokens=0, total_tokens=0,
        )


# ===========================================================================
# Result record
# ===========================================================================

@dataclass
class AgentResult:
    agent_name: str
    stage_key: str
    status: str = "PENDING"       # PASS | FAIL | SKIP
    artifact: Any = None
    error: str = ""
    elapsed_ms: float = 0.0
    verifications: list[tuple[str, bool]] = field(default_factory=list)
    extra_data: dict = field(default_factory=dict)

    def passed(self) -> bool:
        return self.status == "PASS"


# ===========================================================================
# Verification helpers
# ===========================================================================

def _verify(result: AgentResult, label: str, condition: bool) -> None:
    result.verifications.append((label, condition))
    if not condition:
        result.status = "FAIL"


def _verify_artifact(result: AgentResult, artifact: StageArtifact, expected_name: str | None = None) -> None:
    _verify(result, "artifact is StageArtifact", isinstance(artifact, StageArtifact))
    _verify(result, "artifact.content not empty", bool(artifact.content and artifact.content.strip()))
    if expected_name:
        _verify(result, f"artifact.name == '{expected_name}'", artifact.name == expected_name)


# ===========================================================================
# Individual agent runners
# ===========================================================================

def run_domain_researcher(llm, verbose: bool) -> AgentResult:
    from app.agents.domain_researcher import DomainResearcherAgent
    from app.shared.schemas.domain_schema import DomainBrief

    r = AgentResult("DomainResearcherAgent", "domain_research")
    try:
        t0 = time.perf_counter()
        agent = DomainResearcherAgent(llm_manager=llm)
        brief = agent.research("Build a bus booking platform like RedBus")
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify(r, "returns DomainBrief", isinstance(brief, DomainBrief))
        _verify(r, "domain not 'unknown'", brief.domain != "unknown")
        _verify(r, "has standard_modules", len(getattr(brief, "standard_modules", [])) > 0)
        _verify(r, "has standard_actors", len(getattr(brief, "standard_actors", [])) > 0)
        _verify(r, "has common_pitfalls", len(getattr(brief, "common_pitfalls", [])) > 0)

        r.extra_data = {
            "domain": brief.domain,
            "complexity": getattr(brief, "complexity", ""),
            "actors": getattr(brief, "standard_actors", []),
            "modules": getattr(brief, "standard_modules", []),
        }
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = brief
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_clarification(llm, verbose: bool) -> AgentResult:
    from app.agents.clarification import ClarificationAgent

    r = AgentResult("ClarificationAgent", "clarification")
    try:
        t0 = time.perf_counter()
        agent = ClarificationAgent(llm_manager=llm)
        qs = agent.generate_questions(
            "Build a bus booking platform",
            domain_brief={"domain": "transportation", "complexity": "high"},
        )
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        questions = getattr(qs, "questions", [])
        _verify(r, "QuestionSet returned", qs is not None)
        _verify(r, "has ≥1 question", len(questions) >= 1)
        _verify(r, "questions are strings or objects", all(
            isinstance(q, str) or hasattr(q, "question") for q in questions
        ))

        r.extra_data = {"question_count": len(questions),
                        "questions": [getattr(q, "question", str(q)) for q in questions[:3]]}
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = qs
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def _make_simple_agent(cls, llm):
    return cls(llm_manager=llm)


def run_simple_agent(agent_cls, stage_key: str, artifact_name: str, llm, ctx_text: str) -> AgentResult:
    """Generic runner for prompt-builder agents that use execute(context)."""
    r = AgentResult(agent_cls.__name__, stage_key)
    try:
        t0 = time.perf_counter()
        agent = _make_simple_agent(agent_cls, llm)
        ctx = SimpleNamespace(content=ctx_text)
        artifact = agent.execute(ctx)
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, artifact_name)
        r.extra_data = {
            "content_preview": (artifact.content or "")[:120].replace("\n", " "),
            "structured_keys": list(artifact.structured_content.keys()) if artifact.structured_content else [],
        }
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_architect(llm, ctx_text: str) -> AgentResult:
    """ArchitectAgent uses schema validation — needs the canned JSON."""
    from app.agents.architect import ArchitectAgent
    from app.actions.base_action import ActionOutput

    r = AgentResult("ArchitectAgent", "architect")
    try:
        mock_action = MagicMock()
        mock_action.name = "WriteArchitecture"
        arch_json = BUS_BOOKING_CANNED["architect"]
        mock_action.run.return_value = ActionOutput(
            content=arch_json,
            structured=json.loads(arch_json),
        )
        t0 = time.perf_counter()
        agent = ArchitectAgent(llm_manager=llm, primary_action=mock_action)
        artifact = agent.execute(SimpleNamespace(content=ctx_text))
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, "architecture")
        structured = artifact.structured_content or {}
        _verify(r, "has modules", len(structured.get("modules", [])) > 0)
        _verify(r, "has data_models", len(structured.get("data_models", [])) > 0)
        _verify(r, "has tech_stack", bool(structured.get("tech_stack")))
        _verify(r, "has api_endpoints", len(structured.get("api_endpoints", [])) > 0)

        r.extra_data = {
            "tech_stack": structured.get("tech_stack", {}),
            "module_names": [m["name"] for m in structured.get("modules", [])],
            "endpoint_count": len(structured.get("api_endpoints", [])),
            "data_model_names": [m["name"] for m in structured.get("data_models", [])],
        }
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_file_planner(llm, ctx_text: str) -> AgentResult:
    from app.agents.file_planner import FilePlannerAgent

    r = AgentResult("FilePlannerAgent", "file_plan")
    try:
        am = MagicMock()
        am.get_artifact.return_value = None
        t0 = time.perf_counter()
        agent = FilePlannerAgent(llm_manager=llm, artifact_manager=am)
        artifact = agent.execute(SimpleNamespace(content=ctx_text))
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, "file_plan")
        r.extra_data = {
            "content_preview": (artifact.content or "")[:120].replace("\n", " "),
        }
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_developer_agent(agent_cls, stage_key: str, artifact_name: str, llm, file_prefix: str) -> AgentResult:
    """BackendDeveloperAgent / FrontendDeveloperAgent via execute_sprint()."""
    from app.shared.schemas.file_plan_schema import FilePlan, FileSpec

    r = AgentResult(agent_cls.__name__, stage_key)
    try:
        pw = MagicMock()
        pw.write_file = MagicMock(return_value=None)
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])

        agent = agent_cls(llm_manager=llm, project_writer=pw, validator=fv)

        # Build a sprint file plan with bus-booking files
        if file_prefix == "backend":
            files_dict = {
                "backend/models/route.py": FileSpec(file_path="backend/models/route.py", language="python",
                                                     purpose="Route SQLAlchemy model"),
                "backend/services/booking_service.py": FileSpec(file_path="backend/services/booking_service.py",
                                                                 language="python", purpose="Booking service"),
                "backend/api/routes.py": FileSpec(file_path="backend/api/routes.py", language="python",
                                                   purpose="FastAPI route endpoints"),
            }
        else:
            files_dict = {
                "frontend/src/pages/SearchPage.tsx": FileSpec(file_path="frontend/src/pages/SearchPage.tsx",
                                                               language="typescript", purpose="Route search UI"),
                "frontend/src/components/SeatGrid.tsx": FileSpec(file_path="frontend/src/components/SeatGrid.tsx",
                                                                   language="typescript", purpose="Seat selection grid"),
            }

        plan = FilePlan(
            project_id="bus-booking-e2e",
            sprint_number=1,
            sprint_goal=f"Sprint 1 — {file_prefix} foundation",
            generation_order=list(files_dict.keys()),
            files=files_dict,
            tech_stack={"backend": "FastAPI", "frontend": "React"},
        )

        t0 = time.perf_counter()
        result = agent.execute_sprint("bus-booking-e2e", plan)
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify(r, "execute_sprint returned SprintExecutionResult", result is not None)
        _verify(r, "sprint succeeded", result.success)
        _verify(r, f"all {file_prefix} files generated",
                len(result.written_files) == len(files_dict))
        _verify(r, "no failed files", len(result.failed_files) == 0)

        r.extra_data = {
            "sprint_number": result.sprint_number,
            "written": [f.file_path for f in result.written_files],
            "failed": [f.file_path for f in result.failed_files],
        }
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = result
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_qa_agent(llm, ctx_text: str) -> AgentResult:
    from app.agents.qa import QAAgent

    r = AgentResult("QAAgent", "qa")
    try:
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {
            "backend/models/route.py": "class Route(Base): ...",
            "backend/services/booking_service.py": "class BookingService: ...",
        }
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])

        t0 = time.perf_counter()
        agent = QAAgent(llm_manager=llm, project_writer=pw, project_reader=pr, file_validator=fv)
        artifact = agent.execute(SimpleNamespace(content=ctx_text))
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, "qa")
        # QA action writes test files and produces a summary report — check report not raw code
        _verify(r, "content is non-empty string", isinstance(artifact.content, str) and len(artifact.content) > 0)
        r.extra_data = {"content_preview": (artifact.content or "")[:120].replace("\n", " ")}
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_devops_agent(llm, ctx_text: str) -> AgentResult:
    from app.agents.devops import DevOpsAgent

    r = AgentResult("DevOpsAgent", "devops")
    try:
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {"backend/main.py": "from fastapi import FastAPI"}
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])

        t0 = time.perf_counter()
        agent = DevOpsAgent(llm_manager=llm, project_writer=pw, project_reader=pr, file_validator=fv)
        artifact = agent.execute(SimpleNamespace(content=ctx_text))
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, "devops")
        _verify(r, "content contains 'FROM' or 'docker'",
                "FROM" in artifact.content or "docker" in artifact.content.lower())
        r.extra_data = {"content_preview": (artifact.content or "")[:120].replace("\n", " ")}
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


def run_document_agent(llm, ctx_text: str) -> AgentResult:
    from app.agents.document import DocumentAgent

    r = AgentResult("DocumentAgent", "document")
    try:
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {"backend/main.py": "from fastapi import FastAPI"}
        am = MagicMock()
        am.get_artifact.return_value = None

        t0 = time.perf_counter()
        agent = DocumentAgent(llm_manager=llm, project_writer=pw, project_reader=pr, artifact_manager=am)
        artifact = agent.execute(SimpleNamespace(content=ctx_text))
        r.elapsed_ms = (time.perf_counter() - t0) * 1000

        _verify_artifact(r, artifact, "document-output")
        # Document action writes README.md and returns a structured summary artifact
        _verify(r, "content is non-empty string", isinstance(artifact.content, str) and len(artifact.content) > 0)
        r.extra_data = {"content_preview": (artifact.content or "")[:120].replace("\n", " ")}
        if r.status == "PENDING":
            r.status = "PASS"
        r.artifact = artifact
    except Exception as exc:
        r.status = "FAIL"
        r.error = str(exc)
    return r


# ===========================================================================
# Pipeline runner
# ===========================================================================

BUS_BOOKING_REQUEST = (
    "Build a Bus Booking Platform — passengers can search bus routes by origin/destination/date, "
    "view real-time seat availability, select seats interactively, pay via UPI or credit card, "
    "receive an e-ticket with QR code, and cancel bookings with automatic refund."
)

def run_pipeline(verbose: bool = False) -> list[AgentResult]:
    from app.agents.strategic_review import StrategicReviewAgent
    from app.agents.product_owner import ProductOwnerAgent
    from app.agents.designer import DesignerAgent
    from app.agents.security import SecurityAgent
    from app.agents.sprint_planner import SprintPlannerAgent
    from app.agents.scrum_master import ScrumMasterAgent
    from app.agents.retro import RetroAgent
    from app.agents.backend import BackendDeveloperAgent
    from app.agents.frontend import FrontendDeveloperAgent

    llm = _BusBookingLLM()
    ctx = BUS_BOOKING_REQUEST
    results: list[AgentResult] = []

    print(f"\n{_hdr('=' * 70)}")
    print(f"{_hdr('  AI DevOS  —  E2E Test: Bus Booking Platform')}")
    print(f"{_hdr('=' * 70)}")
    print(f"\n{DIM}Scenario: {ctx[:80]}...{RESET}\n")

    pipeline = [
        ("1 / Domain Research",  lambda: run_domain_researcher(llm, verbose)),
        ("2 / Clarification",    lambda: run_clarification(llm, verbose)),
        ("3 / StrategicReview",  lambda: run_simple_agent(StrategicReviewAgent, "strategic_review", "strategic-review-output", llm, ctx)),
        ("4 / ProductOwner",     lambda: run_simple_agent(ProductOwnerAgent, "product_owner", "product-owner-output", llm, ctx)),
        ("5 / Architect",        lambda: run_architect(llm, ctx)),
        ("6 / Designer",         lambda: run_simple_agent(DesignerAgent, "designer", "designer-output", llm, ctx)),
        ("7 / Security",         lambda: run_simple_agent(SecurityAgent, "security", "security-output", llm, ctx)),
        ("8 / SprintPlanner",    lambda: run_simple_agent(SprintPlannerAgent, "sprint_planner", "sprint-plan", llm, ctx)),
        ("9 / ScrumMaster",      lambda: run_simple_agent(ScrumMasterAgent, "scrum_master", "scrum_master", llm, ctx)),
        ("10 / FilePlanner",     lambda: run_file_planner(llm, ctx)),
        ("11 / BackendDeveloper",lambda: run_developer_agent(BackendDeveloperAgent, "backend", "backend", llm, "backend")),
        ("12 / FrontendDeveloper",lambda: run_developer_agent(FrontendDeveloperAgent, "frontend", "frontend", llm, "frontend")),
        ("13 / QA",              lambda: run_qa_agent(llm, ctx)),
        ("14 / DevOps",          lambda: run_devops_agent(llm, ctx)),
        ("15 / Document",        lambda: run_document_agent(llm, ctx)),
        ("16 / Retro",           lambda: run_simple_agent(RetroAgent, "retro", "retro-output", llm, ctx)),
    ]

    for label, runner in pipeline:
        print(f"  {DIM}Running {label}{RESET} ", end="", flush=True)
        result = runner()
        results.append(result)
        status_str = _ok("PASS") if result.passed() else _fail(f"FAIL — {result.error or 'verification failed'}")
        timing = f"{DIM}({result.elapsed_ms:.1f}ms){RESET}"
        print(f"\r  [{status_str}] {label:<30} {timing}")

        if verbose and result.extra_data:
            for k, v in result.extra_data.items():
                print(f"          {DIM}{k}: {v}{RESET}")

        if not result.passed() and result.verifications:
            for check, ok in result.verifications:
                if not ok:
                    print(f"          {_warn('FAIL check:')} {check}")

    return results


# ===========================================================================
# Summary printer
# ===========================================================================

def print_summary(results: list[AgentResult]) -> None:
    passed = sum(1 for r in results if r.passed())
    failed = len(results) - passed
    total  = len(results)

    print(f"\n{_hdr('=' * 70)}")
    print(f"{_hdr('  SUMMARY')}")
    print(f"{_hdr('=' * 70)}")
    print(f"  Agents run : {total}")
    print(f"  {_ok(f'Passed     : {passed}')}")
    if failed:
        print(f"  {_fail(f'Failed     : {failed}')}")

    total_ms = sum(r.elapsed_ms for r in results)
    print(f"  Total time : {total_ms:.1f}ms\n")

    # Detailed table
    print(f"  {'#':<4} {'Agent':<26} {'Status':<8} {'ms':>6}  Verifications")
    print(f"  {'-'*4} {'-'*26} {'-'*8} {'-'*6}  {'-'*30}")
    for i, r in enumerate(results, 1):
        ok_count = sum(1 for _, ok in r.verifications if ok)
        tot      = len(r.verifications)
        checks   = f"{ok_count}/{tot}" if tot else "—"
        stat     = _ok("PASS") if r.passed() else _fail("FAIL")
        print(f"  {i:<4} {r.agent_name:<26} {stat:<8}  {r.elapsed_ms:>5.1f}  {checks}")

    if failed:
        print(f"\n{_fail('SOME AGENTS FAILED')} — see above for details.")
    else:
        print(f"\n{_ok('ALL AGENTS PASSED')} — Bus Booking pipeline is healthy.")

    print()


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="AI DevOS E2E test — Bus Booking scenario")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show artifact previews and extra data")
    args = parser.parse_args()

    results = run_pipeline(verbose=args.verbose)
    print_summary(results)

    return 0 if all(r.passed() for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
