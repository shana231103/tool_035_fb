# File: backend/app/presentation/api/v1/router.py
from fastapi import APIRouter
from app.presentation.api.v1.auth import router as auth_router
from app.presentation.api.v1.browser_status import router as browser_router
from app.presentation.api.v1.control_status import router as controls_router
from app.presentation.api.v1.email_verification import router as verification_router
from app.presentation.api.v1.execution_status import router as execution_router
from app.presentation.api.v1.mailbox_connections import router as mailbox_router
from app.presentation.api.v1.profiles import router as profiles_router
from app.presentation.api.v1.proxies import router as proxies_router
from app.presentation.api.v1.report_tasks import router as tasks_router
from app.presentation.api.v1.retired_jobs import router as retired_jobs_router
from app.presentation.api.v1.task_controls import router as task_controls_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(verification_router)
api_v1_router.include_router(mailbox_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(task_controls_router)
api_v1_router.include_router(execution_router)
api_v1_router.include_router(controls_router)
api_v1_router.include_router(retired_jobs_router)
api_v1_router.include_router(profiles_router)
api_v1_router.include_router(proxies_router)
api_v1_router.include_router(browser_router)
