# File: backend/app/presentation/main.py
from contextlib import asynccontextmanager
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.infrastructure.persistence.database import db_manager
from app.presentation.api.deps import (get_browser_pool, get_queue_orchestrator, get_unit_of_work,
    get_mailbox_sessions, get_mailbox_connections, get_graph_transport, get_storage_service)
from app.presentation.api.local_access import LocalAccessMiddleware, trusted_local_websocket, LocalAccessDenied
from app.presentation.media_routes import router as media_router
from app.infrastructure.persistence.schema_health import check_schema, recover_interrupted
from app.presentation.api.v1.router import api_v1_router
from app.presentation.ws.socket_manager import socket_manager


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

    # Ensure storage subdirectories exist
    os.makedirs(os.path.join(settings.base_storage_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.base_storage_dir, "screenshots"), exist_ok=True)

    # Restore persisted mailbox connections
    try:
        restored = await get_mailbox_connections().restore_from_storage()
        if restored > 0:
            logging.getLogger(__name__).info("Restored %d mailbox connection(s) from persistent storage.", restored)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to restore mailbox connections from storage: %s", exc)

    try:
        yield
    finally:
        socket_manager.close_admission()
        cleanup = (get_mailbox_sessions().shutdown, get_queue_orchestrator().shutdown,
                   socket_manager.shutdown, get_storage_service().shutdown,
                   get_mailbox_connections().shutdown, get_graph_transport().close,
                   get_browser_pool().shutdown, db_manager.close)
        for close in cleanup:
            try:
                await close()
            except Exception:
                logging.getLogger(__name__).warning("Resource cleanup failed.")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Automated Batch Meta Copyright Reporting System",
        version="1.0.0",
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
        if "/mailbox-connections" in request.url.path or "/verification/" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        if "/verification/" in request.url.path or "/mailbox-connections" in request.url.path:
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

    return app


app = create_application()
