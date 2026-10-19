# File: backend/app/presentation/main.py
"""HTTP/WS entry point; task lifecycle is owned by the application lifespan."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.presentation.api.local_access import (
    LocalAccessDenied, LocalAccessMiddleware, trusted_local_websocket,
)
from app.presentation.api.operator_composition import get_auth_service, get_ingress_policy
from app.presentation.api.v1.router import api_v1_router
from app.presentation.media_routes import router as media_router
from app.presentation.spa_routes import register_spa_routes
from app.presentation.task_lifecycle import lifespan
from app.presentation.ws.socket_manager import socket_manager


def create_application() -> FastAPI:
    is_hosted = get_ingress_policy().mode == "hosted"
    app = FastAPI(
        title=settings.app_name,
        description="Automated Standalone Meta Copyright Reporting System",
        version="1.2.0", lifespan=lifespan,
        docs_url=None if is_hosted else "/docs",
        redoc_url=None if is_hosted else "/redoc",
        openapi_url=None if is_hosted else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.add_middleware(LocalAccessMiddleware)
    app.include_router(api_v1_router, prefix="/api")
    app.include_router(media_router)

    @app.middleware("http")
    async def no_store_api(request, call_next):
        response = await call_next(request)
        if "/api/" in request.url.path or any(
            path in request.url.path
            for path in ("/mailbox-connections", "/verification/", "/browser/")
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        if "/api/" in request.url.path:
            return JSONResponse(status_code=422, content={"detail": "Invalid request."})
        return await request_validation_exception_handler(request, error)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        try:
            trusted_local_websocket(websocket)
        except LocalAccessDenied:
            await websocket.close(code=1008)
            return
        policy = get_ingress_policy()
        cookie = websocket.cookies.get(policy.cookie_name)
        if not cookie:
            await websocket.close(code=4401)
            return
        try:
            principal = await get_auth_service().authenticate(cookie)
        except Exception:
            await websocket.close(code=4401)
            return
        if not await socket_manager.connect(websocket, principal=principal):
            return
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return
        finally:
            socket_manager.disconnect(websocket)

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

    register_spa_routes(app)
    return app


app = create_application()
