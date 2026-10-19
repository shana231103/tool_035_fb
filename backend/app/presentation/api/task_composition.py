# File: backend/app/presentation/api/task_composition.py
"""One lifespan-owned execution graph; request handlers never spawn report work."""

from dataclasses import dataclass
import logging
from uuid import UUID, uuid4
from app.application.task_diagnostics import ITaskFailureDiagnostics
from app.infrastructure.persistence.database import db_manager
from app.infrastructure.persistence.sql_unit_of_work import SystemUnitOfWorkFactory
from app.infrastructure.network.proxy_endpoint_policy import ProxyEndpointPolicy
from app.presentation.api import deps
from app.presentation.api.operator_composition import (
    PresentationSystemClock, get_scoped_uow_factory,
)


@dataclass(frozen=True)
class TaskServices:
    runtime_epoch: UUID
    runtime: object
    admission: object
    controls: object
    queries: object
    recovery: object
    operations: object
    coordinator: object
    creator: object


_services: TaskServices | None = None


def build_task_services(factory, *, browser, driver, verification, connections,
                        sessions, notifier, clock, system_factory, proxy_policy,
                        storage, diagnostics: ITaskFailureDiagnostics):
    from app.application.request_authority import RequestAuthorityGuard
    from app.application.execution_authority import ExecutionAuthority
    from app.application.owned_tasks import OwnedTasks
    from app.application.task_admission import TaskAdmissionService
    from app.application.task_runtime import TaskRuntime
    from app.application.task_runtime_drain import TaskRuntimeDrainer
    from app.application.task_execution_coordinator import TaskExecutionCoordinator
    from app.application.task_preparation import TaskPreparation
    from app.application.task_finalization import TaskFinalizer
    from app.application.task_progress import ProgressStore
    from app.application.browser_receipts import BrowserReceiptPersister
    from app.application.operator_controls import OperatorControlService
    from app.application.task_recovery import TaskRecoveryService
    from app.application.task_command_queries import TaskCommandQueries
    from app.application.use_cases.execute_report_task import ExecuteReportTaskUseCase
    from app.application.use_cases.create_report_task import CreateReportTaskUseCase
    from app.application.use_cases.manage_mailbox_connection import ManageMailboxConnectionUseCase

    epoch = uuid4()
    request_authority = RequestAuthorityGuard(clock)
    authority = ExecutionAuthority(clock)
    operations = OwnedTasks(epoch)
    drainer = TaskRuntimeDrainer(factory, browser, authority, clock)
    progress = ProgressStore(factory, notifier, authority)
    receipts = BrowserReceiptPersister(factory)
    finalizer = TaskFinalizer(factory, progress)
    preparation = TaskPreparation(factory, browser, clock, proxy_policy,
                                  connections, authority)
    executor = ExecuteReportTaskUseCase(
        driver, factory, verification, connections, sessions, browser, authority,
    )
    coordinator = TaskExecutionCoordinator(
        preparation, executor, finalizer, progress, receipts,
        drainer, authority, clock, diagnostics=diagnostics,
    )
    runtime = TaskRuntime(factory, coordinator.run, drainer, clock, epoch)
    admission = TaskAdmissionService(factory, runtime, operations,
                                     request_authority, clock, epoch)
    async def disconnect_owned(principal, connection_id):
        flow = ManageMailboxConnectionUseCase(
            connections, sessions, owner=principal.operator_id,
            session_id=principal.session_id,
        )
        await flow.disconnect(connection_id)

    controls = OperatorControlService(factory, runtime, connections,
        operations, request_authority, clock, disconnect_flow=disconnect_owned)
    return TaskServices(
        epoch, runtime, admission, controls, TaskCommandQueries(factory),
        TaskRecoveryService(factory, runtime, system_factory, clock),
        operations, coordinator,
        CreateReportTaskUseCase(factory, storage),
    )


def get_task_services() -> TaskServices:
    global _services
    if _services is None:
        from app.infrastructure.diagnostics.task_failure_frames import trusted_task_failure_frames
        from app.infrastructure.diagnostics.task_failure_logger import LoggingTaskFailureDiagnostics
        _services = build_task_services(
            get_scoped_uow_factory(), browser=deps.get_browser_control(),
            driver=deps.get_automation_driver(),
            verification=deps.get_verification_broker(),
            connections=deps.get_mailbox_connections(),
            sessions=deps.get_mailbox_sessions(), notifier=deps.get_notifier(),
            clock=PresentationSystemClock(),
            system_factory=SystemUnitOfWorkFactory(db_manager),
            proxy_policy=ProxyEndpointPolicy(),
            storage=deps.get_storage_service(),
            diagnostics=LoggingTaskFailureDiagnostics(
                logging.getLogger("app.task_execution"),
                trusted_frames=trusted_task_failure_frames(),
            ),
        )
    return _services


def get_task_runtime():
    return get_task_services().runtime


def get_task_admission_service():
    return get_task_services().admission


def get_operator_controls():
    return get_task_services().controls


def get_task_command_queries():
    return get_task_services().queries


def get_task_recovery():
    return get_task_services().recovery


def get_create_task_use_case():
    return get_task_services().creator


def get_list_tasks_use_case():
    from app.application.use_cases.list_report_tasks import ListReportTasksUseCase
    return ListReportTasksUseCase(get_scoped_uow_factory())


def reset_task_composition() -> None:
    global _services
    if _services is not None and _services.runtime.snapshot().busy:
        raise RuntimeError("Drain task services before resetting their composition.")
    _services = None
