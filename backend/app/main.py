# File: backend/app/main.py
"""
Entrypoint exporting the FastAPI application instance for ASGI servers like Uvicorn.
"""
from app.presentation.main import app

__all__ = ["app"]
