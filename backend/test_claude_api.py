"""Quick standalone test for the Anthropic Claude API.

Run from backend/ directory:
    python test_claude_api.py

Reads CLAUDE_API_KEY from backend/.env (or env).
Tests with a minimal payload — same structure ClaudeProvider sends.
Prints the raw response or the full Anthropic error body.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Load .env so CLAUDE_API_KEY is available when run outside uvicorn
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)  # override=True for test script
        print(f"[info] loaded {env_path}")
except ImportError:
    pass

API_KEY  = os.environ.get("CLAUDE_API_KEY", "")
MODEL    = os.environ.get("LLM_MODEL", "claude-3-5-sonnet-20241022")
BASE_URL = "https://api.anthropic.com"

if not API_KEY:
    print("[FAIL] CLAUDE_API_KEY is not set. Check backend/.env")
    sys.exit(1)

print(f"[info] model  = {MODEL}")
print(f"[info] api_key= {API_KEY[:20]}...{API_KEY[-4:]}")

# ── Build the same payload ClaudeProvider sends ──────────────────────────────
payload = {
    "model": MODEL,
    "max_tokens": 128,
    "temperature": 0.1,
    "system": "You are a helpful assistant.",
    "messages": [
        {"role": "user", "content": "Reply with exactly: {\"ok\": true}"}
    ],
}

print(f"\n[info] payload = {json.dumps({k: v for k, v in payload.items() if k != 'messages'}, indent=2)}")
print(f"[info] messages[0] = {{'role': 'user', 'content': '{payload['messages'][0]['content']}'}}")

req = Request(
    f"{BASE_URL}/v1/messages",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type":      "application/json",
        "x-api-key":         API_KEY,
        "anthropic-version": "2023-06-01",
    },
    method="POST",
)

try:
    with urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    print("\n[PASS] HTTP 200 OK")
    text = "".join(
        b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"
    )
    print(f"[info] response = {text!r}")
    print(f"[info] usage    = {body.get('usage')}")
except HTTPError as exc:
    try:
        error_body = exc.read().decode("utf-8")
    except Exception:
        error_body = "(could not read error body)"
    print(f"\n[FAIL] HTTP {exc.code} {exc.reason}")
    print(f"[info] error_body = {error_body}")
    sys.exit(1)
except Exception as exc:
    print(f"\n[FAIL] {type(exc).__name__}: {exc}")
    sys.exit(1)
