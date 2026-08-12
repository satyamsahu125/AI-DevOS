"""SyntaxValidator — fast, subprocess-light file syntax checking.

Strategy per language:
  Python   → ast.parse()  (stdlib, zero subprocess overhead)
  JS/TS/JSX/TSX → subprocess `node --check` (requires Node on PATH;
                  falls back to brace-balance heuristic if Node absent)
  Everything else → skip (no validator for that extension)

Returns a SyntaxError dataclass describing the first error found, or None
if the file is clean / not checkable.  Callers use this to decide whether
to re-prompt the LLM with the error before writing the file to disk.
"""
from __future__ import annotations

import ast
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions handled by each validator
_PYTHON_EXTS = frozenset({".py", ".pyw"})
_JS_EXTS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

# Cache whether `node` is available so we only probe once per process
_node_available: bool | None = None


def _check_node() -> bool:
    global _node_available
    if _node_available is not None:
        return _node_available
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, timeout=5,
        )
        _node_available = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _node_available = False
    logger.debug("SyntaxValidator: node available=%s", _node_available)
    return _node_available


@dataclass(slots=True)
class SyntaxIssue:
    """Describes a syntax error found in generated file content."""
    path: str
    line: int
    col: int
    message: str

    def as_prompt_hint(self) -> str:
        """Return a short description suitable for injecting into an LLM re-prompt."""
        return (
            f"SYNTAX ERROR in {self.path} at line {self.line}, col {self.col}: {self.message}\n"
            f"Fix this error. Return the COMPLETE corrected file with no other changes."
        )


class SyntaxValidator:
    """Validates generated file content before it is written to disk.

    Usage::

        validator = SyntaxValidator()
        issue = validator.validate("app/main.py", python_source)
        if issue:
            # re-prompt LLM with issue.as_prompt_hint()
            ...
    """

    def validate(self, path: str, content: str) -> SyntaxIssue | None:
        """Return a SyntaxIssue if content has a syntax error, else None."""
        ext = Path(path).suffix.lower()
        if ext in _PYTHON_EXTS:
            return self._validate_python(path, content)
        if ext in _JS_EXTS:
            return self._validate_js(path, content)
        return None  # no validator for this extension

    # ── Python ────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_python(path: str, content: str) -> SyntaxIssue | None:
        """Use stdlib ast.parse — zero subprocess, available everywhere."""
        try:
            ast.parse(content, filename=path)
            return None
        except SyntaxError as exc:
            return SyntaxIssue(
                path=path,
                line=exc.lineno or 0,
                col=exc.offset or 0,
                message=exc.msg or str(exc),
            )
        except Exception as exc:
            # ast.parse can raise other exceptions on extremely malformed input
            return SyntaxIssue(path=path, line=0, col=0, message=str(exc))

    # ── JavaScript / TypeScript ───────────────────────────────────────────────

    def _validate_js(self, path: str, content: str) -> SyntaxIssue | None:
        """Try node --check; fall back to brace-balance heuristic if Node absent."""
        if _check_node():
            return self._validate_js_node(path, content)
        return self._validate_js_heuristic(path, content)

    @staticmethod
    def _validate_js_node(path: str, content: str) -> SyntaxIssue | None:
        """Write content to a temp file and run `node --check` on it.

        node --check parses JS/CommonJS.  For TypeScript we strip type
        annotations with a regex before checking — crude but catches the most
        common structural errors (unmatched braces, missing semicolons in
        critical positions) without needing tsc.
        """
        ext = Path(path).suffix.lower()
        check_content = content
        if ext in (".ts", ".tsx"):
            # Strip TS-only syntax that node can't parse so node --check focuses
            # on structural JS errors rather than tripping on type annotations.
            check_content = _strip_typescript_annotations(content)

        suffix = ".js"  # node --check works on .js files
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(check_content)
                tmp_path = tmp.name

            result = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True, text=True, timeout=10,
            )
            Path(tmp_path).unlink(missing_ok=True)

            if result.returncode == 0:
                return None

            # Parse node's error output: "path:line:col: SyntaxError: msg"
            stderr = result.stderr or result.stdout or ""
            issue = _parse_node_error(path, stderr)
            return issue or SyntaxIssue(path=path, line=0, col=0, message=stderr[:200])

        except subprocess.TimeoutExpired:
            logger.warning("SyntaxValidator: node --check timed out for %s", path)
            return None
        except Exception as exc:
            logger.warning("SyntaxValidator: node --check failed for %s: %s", path, exc)
            return None

    @staticmethod
    def _validate_js_heuristic(path: str, content: str) -> SyntaxIssue | None:
        """Brace/bracket balance check — catches the most obvious structural errors."""
        opens = {"(": ")", "[": "]", "{": "}"}
        closes = set(opens.values())
        stack: list[tuple[str, int]] = []
        in_str: str | None = None
        in_line_comment = False
        in_block_comment = False
        lines = content.splitlines(keepends=True)
        line_no = 0

        for line in lines:
            line_no += 1
            i = 0
            while i < len(line):
                ch = line[i]
                # Block comment handling
                if in_block_comment:
                    if ch == "*" and i + 1 < len(line) and line[i + 1] == "/":
                        in_block_comment = False
                        i += 1
                    i += 1
                    continue
                # Line comment
                if in_line_comment:
                    if ch == "\n":
                        in_line_comment = False
                    i += 1
                    continue
                # String handling (single-line only — good enough for structural check)
                if in_str:
                    if ch == "\\" :
                        i += 2
                        continue
                    if ch == in_str:
                        in_str = None
                    i += 1
                    continue
                # Detect comment starts
                if ch == "/" and i + 1 < len(line):
                    if line[i + 1] == "/":
                        in_line_comment = True
                        i += 2
                        continue
                    if line[i + 1] == "*":
                        in_block_comment = True
                        i += 2
                        continue
                # String openers
                if ch in ("'", '"', "`"):
                    in_str = ch
                    i += 1
                    continue
                # Brackets
                if ch in opens:
                    stack.append((opens[ch], line_no))
                elif ch in closes:
                    if not stack or stack[-1][0] != ch:
                        return SyntaxIssue(
                            path=path,
                            line=line_no,
                            col=i + 1,
                            message=f"Unexpected '{ch}' — mismatched brackets",
                        )
                    stack.pop()
                i += 1

        if stack:
            expected, opened_line = stack[-1]
            return SyntaxIssue(
                path=path,
                line=opened_line,
                col=0,
                message=f"Unclosed bracket, expected '{expected}' (opened at line {opened_line})",
            )
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

_TS_TYPE_ANNOTATION = re.compile(
    r":\s*(?:[A-Za-z_]\w*(?:\s*[<\[|&>][\w\s,.<>\[\]|&?]*)?)\s*(?=[,)=;{])"
)
_TS_GENERIC = re.compile(r"<[^>]*>")
_TS_INTERFACE = re.compile(r"\binterface\s+\w+\s*\{[^}]*\}", re.DOTALL)
_TS_TYPE_KEYWORD = re.compile(r"\btype\s+\w+\s*=\s*[^;]+;")
_TS_AS_CAST = re.compile(r"\bas\s+\w[\w.<>|\[\]]*")


def _strip_typescript_annotations(content: str) -> str:
    """Crudely remove TS-specific syntax so node --check can parse the file.

    This is intentionally simple — we only need to remove enough syntax to
    let node parse the overall structure (braces, function bodies), not to
    produce valid JS.
    """
    result = _TS_INTERFACE.sub("{}", content)
    result = _TS_TYPE_KEYWORD.sub("", result)
    result = _TS_AS_CAST.sub("", result)
    result = _TS_TYPE_ANNOTATION.sub("", result)
    return result


def _parse_node_error(original_path: str, stderr: str) -> SyntaxIssue | None:
    """Extract line/col/message from node's stderr."""
    # Format: /tmp/xxx.js:12\n... SyntaxError: msg
    m = re.search(r":(\d+)\n", stderr)
    line = int(m.group(1)) if m else 0
    m2 = re.search(r"SyntaxError: (.+)", stderr)
    message = m2.group(1).strip() if m2 else stderr[:200].strip()
    if not message:
        return None
    return SyntaxIssue(path=original_path, line=line, col=0, message=message)
