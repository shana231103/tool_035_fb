# File: backend/app/presentation/task_lifecycle.py
"""Initialize authority before recovery and retain dependencies on failed drain."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from app.application.task_drain_diagnostics import drain_stage, emit_drain
from app.core.config import settings
from app.infrastructure.persistence.database import db_manager
from app.infrastructure.persistence.operator_uow import AuthUnitOfWorkFactory
from app.infrastructure.persistence.schema_health import check_schema
from app.presentation.api import deps
from app.presentation.api.operator_composition import PresentationSystemClock, get_auth_service
from app.presentation.api.task_composition import get_task_services
from app.presentation.ws.session_channels import SessionChannelAuthorizer
from app.presentation.ws.socket_manager import socket_manager

logger = logging.getLogger(__name__)


async def shutdown_task_services(services, deadline):
    services.runtime.close_admission()
    with drain_stage("SHUTDOWN_CREATOR"):
        await services.creator.shutdown(deadline)
    with drain_stage("SHUTDOWN_OPERATIONS"):
        services.operations.close_registration()
        census = await services.operations.join(deadline)
        complete = census.complete
        emit_drain("SHUTDOWN_OPERATIONS", census_complete=complete)
        if not complete:
            raise RuntimeError("Task command ownership has not drained.")
    with drain_stage("SHUTDOWN_CONTROLS"):
        await services.controls.shutdown(deadline)
    with drain_stage("SHUTDOWN_RUNTIME"):
        await services.runtime.shutdown(deadline)
    with drain_stage("SHUTDOWN_RUNTIME_CHECK"):
        busy = services.runtime.snapshot().busy
        emit_drain("SHUTDOWN_RUNTIME_CHECK", runtime_busy=busy)
        if busy:
            raise RuntimeError("Task execution ownership remains unresolved.")
    with drain_stage("SHUTDOWN_MAILBOX_SESSIONS"):
        await deps.get_mailbox_sessions().shutdown()


@asynccontextmanager
async def lifespan(app):
    clock = PresentationSystemClock()
    db_manager.init(settings.database_url, echo=settings.database_echo)
    try:
        await check_schema(db_manager)
    except BaseException:
        await db_manager.close()
        raise

    socket_manager.configure(
        max_clients=settings.ws_max_clients, queue_size=settings.ws_queue_size,
        max_payload_bytes=settings.ws_max_payload_bytes,
        send_timeout=settings.ws_send_timeout, close_timeout=settings.ws_close_timeout,
    )
    services = get_task_services()
    authorizer = None
    try:
        # Browser bootstrap owns the exclusive installation authority and ledger census.
        await deps.get_browser_control().bootstrap()
        await services.recovery.classify_startup(services.runtime_epoch)
        authorizer = SessionChannelAuthorizer(
            auth_service=get_auth_service(),
            auth_factory=AuthUnitOfWorkFactory(db_manager._sessionmaker),
            clock=clock, manager=socket_manager,
        )
        socket_manager.set_authorizer(authorizer)
        authorizer.start_sweeper()
        for folder in ("uploads", "screenshots"):
            (Path(settings.base_storage_dir) / folder).mkdir(parents=True, exist_ok=True)
        yield
    finally:
        socket_manager.close_admission()
        if authorizer is not None:
            with drain_stage("SHUTDOWN_AUTHORIZER"):
                await authorizer.shutdown()
        try:
            with drain_stage("SHUTDOWN_TASK_SERVICES"):
                await shutdown_task_services(services, clock.monotonic() + 10)
            with drain_stage("SHUTDOWN_MAILBOX_CONNECTIONS"):
                await deps.get_mailbox_connections().shutdown()
        except BaseException:
            logger.warning("Task drain incomplete; provider and database authority retained.")
            raise
        with drain_stage("SHUTDOWN_SOCKET"):
            await socket_manager.shutdown()
        with drain_stage("SHUTDOWN_STORAGE"):
            await deps.get_storage_service().shutdown()
        with drain_stage("SHUTDOWN_GRAPH"):
            await deps.get_graph_transport().close()
        try:
            with drain_stage("SHUTDOWN_BROWSER"):
                await deps.get_browser_control().shutdown()
        except BaseException:
            logger.warning("Browser drain incomplete; database authority retained.")
            raise
        with drain_stage("SHUTDOWN_DATABASE"):
            await db_manager.close()
