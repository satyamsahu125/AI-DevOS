from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Parsed metadata for one generated project file."""

    file_path: str          # relative: "backend/models/user.py"
    language: str           # "python" | "typescript" | "yaml" …
    purpose: str            # one-line summary from docstring/comment
    classes: list[str]      # ["UserModel", "UserSchema"]
    functions: list[str]    # ["get_user(id)", "create_user()"]
    imports: list[str]      # all imported modules
    exports: list[str]      # exported names (JS/TS)
    dependencies: list[str] # project-internal imports only
    line_count: int
    size_bytes: int
    last_updated: str
    sprint_number: int


class FileIndexer:
    """Automatically indexes every generated project file.

    Called by ProjectWriter after each file write.
    No LLM calls — pure static analysis (AST for Python,
    regex for JS/TS).

    Answers questions like:
      "Where is authentication handled?"
      "What imports UserRepository?"
      "What changed in sprint 2?"
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS file_index (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id    TEXT NOT NULL,
                file_path     TEXT NOT NULL,
                language      TEXT NOT NULL,
                purpose       TEXT DEFAULT '',
                classes       TEXT DEFAULT '[]',
                functions     TEXT DEFAULT '[]',
                imports       TEXT DEFAULT '[]',
                exports       TEXT DEFAULT '[]',
                dependencies  TEXT DEFAULT '[]',
                line_count    INTEGER DEFAULT 0,
                size_bytes    INTEGER DEFAULT 0,
                sprint_number INTEGER DEFAULT 0,
                last_updated  TEXT NOT NULL,
                UNIQUE(project_id, file_path)
            );
            CREATE INDEX IF NOT EXISTS idx_file_index_project
              ON file_index(project_id);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(
        self,
        project_id: str,
        file_path: str,
        content: str,
        sprint_number: int = 0,
    ) -> FileMetadata:
        """Parse and index one file.

        Called automatically after every file write.  The result is
        upserted into the SQLite ``file_index`` table so re-indexing the
        same path (e.g. after a retry-rewrite) keeps only the latest
        version.
        """
        language = self._detect_language(file_path)
        metadata = self._parse_file(file_path, content, language)
        metadata.sprint_number = sprint_number
        metadata.last_updated = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO file_index
              (project_id, file_path, language, purpose,
               classes, functions, imports, exports,
               dependencies, line_count, size_bytes,
               sprint_number, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id, file_path)
            DO UPDATE SET
              purpose=excluded.purpose,
              classes=excluded.classes,
              functions=excluded.functions,
              imports=excluded.imports,
              exports=excluded.exports,
              dependencies=excluded.dependencies,
              line_count=excluded.line_count,
              size_bytes=excluded.size_bytes,
              sprint_number=excluded.sprint_number,
              last_updated=excluded.last_updated
            """,
            (
                project_id,
                file_path,
                language,
                metadata.purpose,
                json.dumps(metadata.classes),
                json.dumps(metadata.functions),
                json.dumps(metadata.imports),
                json.dumps(metadata.exports),
                json.dumps(metadata.dependencies),
                metadata.line_count,
                metadata.size_bytes,
                sprint_number,
                metadata.last_updated,
            ),
        )
        self._conn.commit()
        logger.debug(
            "Indexed %s: %d classes, %d functions",
            file_path,
            len(metadata.classes),
            len(metadata.functions),
        )
        return metadata

    def get_project_index(self, project_id: str) -> list[FileMetadata]:
        """Return all indexed files for *project_id*, ordered by path."""
        rows = self._conn.execute(
            """
            SELECT file_path, language, purpose,
                   classes, functions, imports, exports,
                   dependencies, line_count, size_bytes,
                   sprint_number, last_updated
            FROM file_index
            WHERE project_id = ?
            ORDER BY file_path
            """,
            (project_id,),
        ).fetchall()
        return [
            FileMetadata(
                file_path=r[0],
                language=r[1],
                purpose=r[2],
                classes=json.loads(r[3]),
                functions=json.loads(r[4]),
                imports=json.loads(r[5]),
                exports=json.loads(r[6]),
                dependencies=json.loads(r[7]),
                line_count=r[8],
                size_bytes=r[9],
                sprint_number=r[10],
                last_updated=r[11],
            )
            for r in rows
        ]

    def search_by_class(self, project_id: str, class_name: str) -> list[FileMetadata]:
        """Find files that define *class_name*."""
        rows = self._conn.execute(
            """
            SELECT file_path, language, purpose,
                   classes, functions, imports, exports,
                   dependencies, line_count, size_bytes,
                   sprint_number, last_updated
            FROM file_index
            WHERE project_id = ?
              AND classes LIKE ?
            """,
            (project_id, f'%"{class_name}"%'),
        ).fetchall()
        return [
            FileMetadata(
                file_path=r[0],
                language=r[1],
                purpose=r[2],
                classes=json.loads(r[3]),
                functions=json.loads(r[4]),
                imports=json.loads(r[5]),
                exports=json.loads(r[6]),
                dependencies=json.loads(r[7]),
                line_count=r[8],
                size_bytes=r[9],
                sprint_number=r[10],
                last_updated=r[11],
            )
            for r in rows
        ]

    def search_by_function(self, project_id: str, function_name: str) -> list[str]:
        """Return file paths that contain *function_name*."""
        rows = self._conn.execute(
            """
            SELECT file_path FROM file_index
            WHERE project_id = ?
              AND functions LIKE ?
            """,
            (project_id, f"%{function_name}%"),
        ).fetchall()
        return [r[0] for r in rows]

    def get_file_summary(self, project_id: str, file_path: str) -> str:
        """Return a compact human-readable summary for context injection."""
        row = self._conn.execute(
            """
            SELECT purpose, classes, functions, dependencies, line_count
            FROM file_index
            WHERE project_id = ? AND file_path = ?
            """,
            (project_id, file_path),
        ).fetchone()

        if not row:
            return f"{file_path}: (not indexed)"

        purpose, classes_raw, funcs_raw, deps_raw, lines = row
        classes_list = json.loads(classes_raw)
        funcs_all = json.loads(funcs_raw)
        funcs_list = funcs_all[:5]
        deps_list = json.loads(deps_raw)[:3]

        parts = [f"{file_path} ({lines} lines)"]
        parts.append(f"  Purpose: {purpose or 'not documented'}")
        if classes_list:
            parts.append(f"  Classes: {', '.join(classes_list)}")
        if funcs_list:
            ellipsis = "..." if len(funcs_all) > 5 else ""
            parts.append(f"  Functions: {', '.join(funcs_list)}{ellipsis}")
        if deps_list:
            parts.append(f"  Depends on: {', '.join(deps_list)}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal parsing helpers
    # ------------------------------------------------------------------

    def _parse_file(self, file_path: str, content: str, language: str) -> FileMetadata:
        meta = FileMetadata(
            file_path=file_path,
            language=language,
            purpose="",
            classes=[],
            functions=[],
            imports=[],
            exports=[],
            dependencies=[],
            line_count=content.count("\n"),
            size_bytes=len(content.encode()),
            last_updated="",
            sprint_number=0,
        )
        if language == "python":
            self._parse_python(content, meta)
        elif language in ("typescript", "javascript"):
            self._parse_js(content, meta)
        meta.purpose = self._extract_purpose(content, language)
        return meta

    def _parse_python(self, content: str, meta: FileMetadata) -> None:
        """Parse Python with the stdlib ``ast`` module."""
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            logger.debug("Python parse error in %s: %s", meta.file_path, exc)
            return

        # Collect class-level method names so we can exclude them from
        # the top-level function list (they already live inside a class).
        method_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                meta.classes.append(node.name)
                for child in ast.walk(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_nodes.add(id(child))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if id(node) not in method_nodes:
                    args = [a.arg for a in node.args.args]
                    meta.functions.append(f"{node.name}({', '.join(args)})")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    meta.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    meta.imports.append(node.module)
                    # Identify project-internal imports
                    if (
                        node.level > 0  # relative import
                        or node.module.startswith("app.")
                        or node.module.startswith("backend.")
                    ):
                        meta.dependencies.append(node.module)

    def _parse_js(self, content: str, meta: FileMetadata) -> None:
        """Parse JS/TS with regex (avoids an npm/esprima dependency)."""
        meta.classes = re.findall(r"(?:export\s+)?class\s+(\w+)", content)

        raw_fns = re.findall(
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
            content,
        )
        meta.functions = [f"{name}({args})" for name, args in raw_fns]

        arrows = re.findall(
            r"export\s+const\s+(\w+)\s*=\s*(?:async\s+)?\(",
            content,
        )
        meta.functions.extend(arrows)

        for imp in re.findall(
            r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content
        ):
            meta.imports.append(imp)
            if imp.startswith(".") or imp.startswith("@/"):
                meta.dependencies.append(imp)

        meta.exports = re.findall(
            r"export\s+(?:default\s+)?(?:class|function|const|type)\s+(\w+)",
            content,
        )

    def _extract_purpose(self, content: str, language: str) -> str:
        """Return the first module-level docstring or comment (≤120 chars)."""
        if language == "python":
            m = re.search(r'"""(.+?)"""', content, re.DOTALL)
            if m:
                return m.group(1).strip()[:120]
            m = re.search(r"'''(.+?)'''", content, re.DOTALL)
            if m:
                return m.group(1).strip()[:120]
        m = re.search(r"/\*\*?\s*(.+?)\s*\*/", content, re.DOTALL)
        if m:
            return m.group(1).strip()[:120]
        m = re.search(r"#\s*(.+)", content)
        if m:
            return m.group(1).strip()[:120]
        return ""

    def _detect_language(self, file_path: str) -> str:
        return {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
        }.get(Path(file_path).suffix.lower(), "text")
