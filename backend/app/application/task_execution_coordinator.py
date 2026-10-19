# File: backend/app/application/task_execution_coordinator.py
"""Own business completion; the runtime owns the subsequent resource drain."""
import asyncio
from app.application.owned_tasks import current_stop_request
from app.application.task_diagnostics import ITaskFailureDiagnostics, TaskAttemptTrace, TaskStage
from app.application.task_failure_policy import classify_task_failure

from app.application.task_runtime_records import ExecutionOutcome
from app.domain.value_objects.enums import TaskStatus


class TaskExecutionCoordinator:
    def __init__(self, preparation, executor, finalizer, progress, receipt, drainer, authority, clock,
                 *, diagnostics: ITaskFailureDiagnostics):
        self._preparation, self._executor, self._finalizer = preparation, executor, finalizer
        self._progress, self._receipt, self._clock = progress, receipt, clock
        self._diagnostics = diagnostics

    async def run(self, grant):
        trace = TaskAttemptTrace(grant)
        try:
            if current_stop_request.get()():
                raise asyncio.CancelledError
            prepared = await self._preparation.prepare(grant, self._clock.monotonic() + 30,
                                                       trace=trace)
            trace.enter(TaskStage.BEGIN_ATTEMPT)
            await self._finalizer.begin_attempt(grant, prepared)

            async def progress(status, metadata):
                await self._progress.persist(grant, status, metadata)

            async def receipt(evidence):
                task = await self._receipt.persist(grant, evidence)
                await self._progress.notify(task)

            trace.enter(TaskStage.EXECUTE)
            outcome = await self._executor.execute(grant, prepared, progress=progress, receipt=receipt)
        except asyncio.CancelledError:
            outcome = ExecutionOutcome(TaskStatus.CANCELLED, "STOP_REQUESTED")
        except Exception as error:
            failure = self._record_failure(trace, error)
            outcome = ExecutionOutcome(TaskStatus.FAILED, failure.code.value)
        trace.enter(TaskStage.FINALIZE)
        try:
            await self._finalizer.finalize(grant, outcome)
        except Exception as error:
            self._record_failure(trace, error)
            raise

    def _record_failure(self, trace, error):
        failure = classify_task_failure(trace.stage, error)
        try:
            self._diagnostics.record_failure(trace.failure_context(failure), error)
        except Exception:
            # Diagnostic sink failures must not suppress business finalization.
            return failure
        return failure
