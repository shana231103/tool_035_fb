# File: backend/app/infrastructure/diagnostics/task_failure_frames.py
"""Only explicitly registered code objects may supply diagnostic source locations."""
from dataclasses import dataclass
from types import CodeType, FrameType, MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SafeDiagnosticFrameLabel:
    module: str
    function: str


def trusted_task_failure_frames() -> Mapping[CodeType, SafeDiagnosticFrameLabel]:
    from app.application.execution_authority import ExecutionAuthority
    from app.application.task_execution_coordinator import TaskExecutionCoordinator
    from app.application.task_preparation import TaskPreparation
    from app.application.task_finalization import TaskFinalizer
    from app.infrastructure.persistence.repositories.task_execution_repo import SqlTaskExecutionRepository
    from app.infrastructure.persistence.repositories.postgres_profile_repo import PostgresProfileRepository
    from app.infrastructure.persistence.repositories.postgres_task_repo import PostgresTaskRepository
    entries = (
        (TaskExecutionCoordinator.run, "application.task_execution_coordinator", "run"),
        (TaskPreparation.prepare, "application.task_preparation", "prepare"),
        (TaskFinalizer.begin_attempt, "application.task_finalization", "begin_attempt"),
        (TaskFinalizer._finalize, "application.task_finalization", "finalize"),
        (ExecutionAuthority.require_run, "application.execution_authority", "require_run"),
        (ExecutionAuthority.match_grant, "application.execution_authority", "match_grant"),
        (SqlTaskExecutionRepository.read, "persistence.task_execution_repo", "read"),
        (PostgresProfileRepository.get_by_id, "persistence.profile_repo", "get_by_id"),
        (PostgresTaskRepository.get_by_id, "persistence.task_repo", "get_by_id"),
    )
    return MappingProxyType({method.__code__: SafeDiagnosticFrameLabel(module, name)
                             for method, module, name in entries})


def safe_diagnostic_frame(frame: FrameType, line: int,
                          registry: Mapping[CodeType, SafeDiagnosticFrameLabel]) -> dict:
    for code, label in registry.items():
        if frame.f_code is code and type(code) is CodeType:
            if line in {number for _, _, number in code.co_lines() if number is not None}:
                return {"module": label.module, "function": label.function, "line": line}
    return {"module": "EXTERNAL_FRAME", "function": "EXTERNAL_FRAME", "line": 0}
