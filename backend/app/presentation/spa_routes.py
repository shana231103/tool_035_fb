# File: backend/app/presentation/spa_routes.py
"""SPA static serving with strict directory confinement and security headers."""

import os
import stat
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_SPA_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _reparse(path: Path) -> bool:
    try:
        info = path.lstat()
        return path.is_symlink() or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        )
    except OSError:
        return True


def is_safe_dist_path(base_dir: Path, target: Path) -> bool:
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target.resolve()
        resolved_target.relative_to(resolved_base)
        if _reparse(target) or _reparse(resolved_target):
            return False
        return True
    except (ValueError, OSError):
        return False


def find_frontend_dist() -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "frontend" / "dist")
        candidates.append(Path(sys._MEIPASS) / "dist")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "frontend" / "dist")
        candidates.append(exe_dir / "_internal" / "frontend" / "dist")
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.append(project_root / "frontend" / "dist")
    candidates.append(Path.cwd() / "frontend" / "dist")
    candidates.append(Path.cwd().parent / "frontend" / "dist")

    for path in candidates:
        if path.is_dir() and (path / "index.html").is_file():
            return path
    return None


def register_spa_routes(app: FastAPI, dist_dir: Path | None = None) -> None:
    if dist_dir is None:
        dist_dir = find_frontend_dist()
    if not dist_dir:
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if (
            full_path.startswith(("api/", "api", "static/", "ws"))
            or full_path in ("docs", "redoc", "openapi.json")
        ):
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        if full_path:
            file_target = dist_dir / full_path
            if file_target.is_file():
                if not is_safe_dist_path(dist_dir, file_target):
                    return JSONResponse(
                        status_code=404, content={"detail": "Not found"}
                    )
                return FileResponse(file_target)

        index_target = dist_dir / "index.html"
        if index_target.is_file() and is_safe_dist_path(dist_dir, index_target):
            return FileResponse(index_target, headers=_SPA_HEADERS)
        return JSONResponse(status_code=404, content={"detail": "Not found"})
