# File: backend/app/presentation/task_lifecycle.py
"""Initialize authority before recovery and retain dependencies on failed drain."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
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
    await services.creator.shutdown(deadline)
    services.operations.close_registration()
    census = await services.operations.join(deadline)
    if not census.complete:
        raise RuntimeError("Task command ownership has not drained.")
    await services.controls.shutdown(deadline)
    await services.runtime.shutdown(deadline)
    if services.runtime.snapshot().busy:
        raise RuntimeError("Task execution ownership remains unresolved.")
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
            await authorizer.shutdown()
        try:
            await shutdown_task_services(services, clock.monotonic() + 10)
            await deps.get_mailbox_connections().shutdown()
        except BaseException:
            logger.warning("Task drain incomplete; provider and database authority retained.")
            raise
        await socket_manager.shutdown()
        await deps.get_storage_service().shutdown()
        await deps.get_graph_transport().close()
        try:
            await deps.get_browser_control().shutdown()
        except BaseException:
            logger.warning("Browser drain incomplete; database authority retained.")
            raise
        await db_manager.close()
