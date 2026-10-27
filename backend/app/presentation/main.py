# File: backend/app/presentation/main.py
from contextlib import asynccontextmanager
import os
import sys
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.infrastructure.persistence.database import db_manager
from app.presentation.api.deps import (get_browser_control, get_queue_orchestrator, get_unit_of_work,
    get_mailbox_sessions, get_mailbox_connections, get_graph_transport, get_storage_service)
from app.presentation.api.local_access import LocalAccessMiddleware, trusted_local_websocket, LocalAccessDenied
from app.presentation.media_routes import router as media_router
from app.infrastructure.persistence.schema_health import check_schema, recover_interrupted
from app.presentation.api.v1.router import api_v1_router
from app.presentation.ws.socket_manager import socket_manager
from app.presentation.api.bulk_composition import shutdown_bulk_imports


@asynccontextmanager
async def lifespan(app: FastAPI):
    socket_manager.configure(max_clients=settings.ws_max_clients, queue_size=settings.ws_queue_size,
        max_payload_bytes=settings.ws_max_payload_bytes, send_timeout=settings.ws_send_timeout,
        close_timeout=settings.ws_close_timeout)
    # Startup: initialize database engine and ensure tables exist
    db_manager.init(settings.database_url, echo=settings.database_echo)
    await db_manager.create_all_tables()
    await check_schema(db_manager)
    await recover_interrupted(get_unit_of_work)
    await get_browser_control().bootstrap()

    # Ensure storage subdirectories exist
    os.makedirs(os.path.join(settings.base_storage_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.base_storage_dir, "screenshots"), exist_ok=True)

    try:
        yield
    finally:
        socket_manager.close_admission()
        get_queue_orchestrator().close_admission()
        try:
            await shutdown_bulk_imports()
            await get_mailbox_sessions().shutdown()
            await get_queue_orchestrator().shutdown()
        except BaseException:
            logging.getLogger(__name__).warning("Task shutdown incomplete; browser and persistence remain available.")
            raise
        cleanup = (socket_manager.shutdown, get_storage_service().shutdown,
                   get_mailbox_connections().shutdown, get_graph_transport().close)
        for close in cleanup:
            try:
                await close()
            except Exception:
                logging.getLogger(__name__).warning("Resource cleanup failed.")
        try:
            await get_browser_control().shutdown()
        except BaseException:
            logging.getLogger(__name__).warning("Browser shutdown incomplete; persistence remains available.")
            raise
        await db_manager.close()


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Automated Batch Meta Copyright Reporting System",
        version="1.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalAccessMiddleware)

    # API Routers
    app.include_router(api_v1_router, prefix="/api")
    app.include_router(media_router)

    @app.middleware("http")
    async def no_store_mailbox(request, call_next):
        response = await call_next(request)
        if any(path in request.url.path for path in ("/mailbox-connections", "/verification/", "/browser/", "/jobs/bulk")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        if any(path in request.url.path for path in ("/mailbox-connections", "/verification/", "/browser/", "/jobs/bulk")):
            return JSONResponse(status_code=422, content={"detail": "Invalid request."})
        return await request_validation_exception_handler(request, error)

    # Real-time WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        try:
            trusted_local_websocket(websocket)
        except LocalAccessDenied:
            await websocket.close(code=1008)
            return
        if not await socket_manager.connect(websocket):
            return
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return
        finally:
            socket_manager.disconnect(websocket)

    # Health check
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

    dist_dir = _find_frontend_dist()
    if dist_dir:
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_frontend(full_path: str):
            if full_path.startswith(("api/", "api", "static/", "ws")):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            if full_path:
                file_target = dist_dir / full_path
                if file_target.is_file():
                    return FileResponse(file_target)
            index_target = dist_dir / "index.html"
            if index_target.is_file():
                return FileResponse(index_target)
            return JSONResponse(status_code=404, content={"detail": "Not found"})

    return app


def _find_frontend_dist() -> Path | None:
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


app = create_application()
