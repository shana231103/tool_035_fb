# File: backend/app/presentation/api/v1/router.py
from fastapi import APIRouter
from app.presentation.api.v1.jobs import router as jobs_router
from app.presentation.api.v1.profiles import router as profiles_router
from app.presentation.api.v1.proxies import router as proxies_router
from app.presentation.api.v1.mailbox_connections import router as mailbox_router

api_v1_router = APIRouter(prefix="/v1")
from app.presentation.api.v1.email_verification import router as verification_router
api_v1_router.include_router(verification_router)
api_v1_router.include_router(mailbox_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(profiles_router)
api_v1_router.include_router(proxies_router)
