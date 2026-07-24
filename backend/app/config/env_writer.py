from __future__ import annotations

from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def upsert_env_values(values: dict[str, str], path: Path = _ENV_PATH) -> None:
    """Persist key=value pairs into the .env file, replacing any existing lines for those keys."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            updated_lines.append(line)
            continue
        key = stripped.split("=", 1)[0]
        if key in remaining:
            updated_lines.append(f"{key}={remaining.pop(key)}")
        else:
            updated_lines.append(line)
    for key, value in remaining.items():
        updated_lines.append(f"{key}={value}")
    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
