"""Project Intelligence API — file index, dependency graph, and codebase search endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..kernel.container import Container
from .dependencies import get_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/intelligence", tags=["intelligence"])


# ---------------------------------------------------------------------------
# GET /intelligence/files
# ---------------------------------------------------------------------------
@router.get("/files")
def get_file_index(project_id: str, container: Annotated[Container, Depends(get_container)]):
    """Return the full file index for a project — all parsed metadata per file."""
    try:
        indexer = container.resolve("file_indexer")
        files = indexer.get_project_index(project_id)
        return {
            "project_id": project_id,
            "total_files": len(files),
            "files": [
                {
                    "file_path": f.file_path,
                    "language": f.language,
                    "purpose": f.purpose,
                    "classes": f.classes,
                    "functions": f.functions,
                    "dependencies": f.dependencies,
                    "line_count": f.line_count,
                    "size_bytes": f.size_bytes,
                    "sprint_number": f.sprint_number,
                    "last_updated": f.last_updated,
                }
                for f in files
            ],
        }
    except Exception as exc:
        logger.exception("file_index error: project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /intelligence/dependencies
# ---------------------------------------------------------------------------
@router.get("/dependencies")
def get_dependencies(project_id: str, container: Annotated[Container, Depends(get_container)]):
    """Return the dependency graph, most-depended-on files, and entry points."""
    try:
        dep_graph = container.resolve("dependency_graph")
        graph = dep_graph.build(project_id)
        most_used = dep_graph.get_most_depended_on(project_id, top_n=10)
        entry_points = dep_graph.get_entry_points(project_id)
        return {
            "project_id": project_id,
            "most_depended_on": [
                {"file": path, "used_by": count} for path, count in most_used
            ],
            "entry_points": entry_points,
            "graph": graph,
        }
    except Exception as exc:
        logger.exception("dependencies error: project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /intelligence/overview
# ---------------------------------------------------------------------------
@router.get("/overview")
def get_overview(project_id: str, container: Annotated[Container, Depends(get_container)]):
    """Return a compact human-readable project overview (grouped by directory)."""
    try:
        summarizer = container.resolve("code_summarizer")
        overview = summarizer.build_project_overview(project_id, max_files=30)
        return {"project_id": project_id, "overview": overview}
    except Exception as exc:
        logger.exception("overview error: project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /intelligence/search
# ---------------------------------------------------------------------------
@router.get("/search")
def search_files(
    project_id: str,
    container: Annotated[Container, Depends(get_container)],
    q: str = Query(..., description="Search query — keywords describing what you need"),
    type: str = Query("any", description="Filter type: 'class', 'function', or 'any'"),
    limit: int = Query(10, ge=1, le=50),
):
    """Find files relevant to a query using keyword matching on class/function/purpose metadata."""
    try:
        indexer = container.resolve("file_indexer")
        summarizer = container.resolve("code_summarizer")

        if type == "class":
            results = indexer.search_by_class(project_id, q)
            file_paths = [r.file_path if hasattr(r, "file_path") else r[1] for r in results]
        elif type == "function":
            file_paths = indexer.search_by_function(project_id, q)
        else:
            file_paths = summarizer.get_relevant_files(project_id, q, max_files=limit)

        return {
            "project_id": project_id,
            "query": q,
            "type": type,
            "relevant_files": file_paths[:limit],
            "count": len(file_paths[:limit]),
        }
    except Exception as exc:
        logger.exception("search error: project_id=%s q=%s", project_id, q)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /intelligence/impact
# ---------------------------------------------------------------------------
@router.get("/impact")
def get_impact(
    project_id: str,
    container: Annotated[Container, Depends(get_container)],
    file: str = Query(..., description="File path to analyse impact for"),
):
    """Return all files that would be affected if the given file changes (BFS traversal)."""
    try:
        dep_graph = container.resolve("dependency_graph")
        affected = dep_graph.get_impact(project_id, file)
        direct = dep_graph.get_dependencies_of(project_id, file)
        return {
            "project_id": project_id,
            "changed_file": file,
            "direct_dependencies": direct,
            "affected_files": affected,
            "total_affected": len(affected),
        }
    except Exception as exc:
        logger.exception("impact error: project_id=%s file=%s", project_id, file)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
