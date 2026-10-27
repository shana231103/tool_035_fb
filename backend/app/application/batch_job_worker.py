# File: backend/app/application/batch_job_worker.py
import asyncio
import logging
import random
from app.application.batch_dispatch import BatchDispatch
from app.application.dispatch_admission import DispatchAdmission
from app.application.dispatch_claim import settle_owned
from app.application.dispatch_drain import DispatchDrain
from app.application.execution_budget import ExecutionBudget
from app.application.execution_context import (
    AdmissionOutcomeUnknown, JobRunGate, UnusedPermitConfirmed,
)
from app.application.task_finalization import TaskFinalizer
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.enums import JobStatus, TaskStatus

logger = logging.getLogger(__name__)


class BatchJobWorker:
    """One bounded dispatcher, email owner and drain budget shared by all jobs."""

    def __init__(self, uow_factory, executor, progress, verification, max_contexts,
                 email_slot_timeout, notifier, browser_control=None, *, connections=None,
                 sessions=None, collector=None):
        self._factory, self._executor, self._progress = uow_factory, executor, progress
        self._verification, self._notifier, self._browser = verification, notifier, browser_control
        self.connections = connections
        self.budget = ExecutionBudget(min(3, max_contexts))
        self._finalizer = TaskFinalizer(uow_factory, progress)
        self.admission = DispatchAdmission(uow_factory, connections, sessions, self._finalizer,
                                           browser_control)
        self.drain = DispatchDrain(uow_factory, self.budget, sessions, verification,
                                   browser_control, collector)
        self._bootstrap_lock, self._bootstrapped = asyncio.Lock(), False
        self._gates = {}

    async def ensure_bootstrap(self):
        async with self._bootstrap_lock:
            if not self._bootstrapped:
                await self.drain.bootstrap()
                self._bootstrapped = True

    async def notify_job(self, job):
        try:
            payload = {"status": job.status.value, "stats": job.calculate_stats()}
            if job.bulk:
                payload.update(import_id=str(job.bulk.import_id), bulk_revision=job.bulk.revision,
                               bulk_pause_reason=job.bulk.pause_reason)
            await self._notifier.broadcast_job_update(str(job.id), payload)
        except Exception:
            logger.warning("Job notification failed after persistence: %s", job.id)

    async def run(self, job, profile):
        gate = JobRunGate(job.id, job.bulk.accepted_profile_sha256 if job.bulk else None)
        self._gates[job.id] = gate
        try:
            await BatchDispatch(self).run(job.id, gate)
        finally:
            if self._gates.get(job.id) is gate:
                self._gates.pop(job.id, None)

    def close_job(self, job_id):
        gate = self._gates.get(job_id)
        if gate:
            gate.close()

    async def _refresh_job(self, job_id):
        async with self._factory() as uow:
            fresh = await uow.jobs.get_by_id(job_id)
            if fresh.status != JobStatus.RUNNING:
                return fresh.status
            fresh.update_completion_status()
            await uow.jobs.save(fresh)
        await self.notify_job(fresh)
        return fresh.status

    async def _fail_context(self, context):
        async with self._factory() as uow:
            current = await uow.tasks.get_by_id(context.task_id)
        if current and current.attempt_id == context.attempt_id:
            current.mark_failed("EXECUTION_FAILED", False)
            current.verification = {}
            await self._finalizer.finalize(current)

    async def _execute_reserved(self, permit, job, gate):
        context, proof, unknown = None, None, False
        try:
            async with self._factory() as uow:
                proxy = await uow.proxies.get_active_proxy(job.preferred_country)
            prepared = await self.admission.prepare(permit.task_id, gate, permit, proxy)
            if isinstance(prepared, UnusedPermitConfirmed):
                proof = prepared
                return None
            context = prepared
            self.budget.bind_attempt(permit, context.attempt_id)
            async with self._factory() as uow:
                task = await uow.tasks.get_by_id(permit.task_id)
                profile = await uow.profiles.get_by_id(job.owner_profile_id)
            result = await self._executor.execute(task, profile, proxy, context=context)
            if proxy and (result.retryable or task.status == TaskStatus.SUBMITTED):
                if result.retryable:
                    proxy.mark_failed()
                else:
                    proxy.mark_active(proxy.latency_ms)
                async with self._factory() as uow:
                    await uow.proxies.save(proxy)
            return None
        except AdmissionOutcomeUnknown:
            unknown = True
            return "ADMISSION_OUTCOME_UNKNOWN"
        except MailboxError:
            if context:
                await self._fail_context(context)
            return None
        except asyncio.CancelledError:
            record = self.admission.records.get(permit.id)
            if context and not context.trace.driver_entered and record:
                try:
                    proof, _ = await settle_owned(self.admission._undo(permit, record, applied=True))
                except Exception:
                    unknown = True
            elif context:
                async with self._factory() as uow:
                    task = await uow.tasks.get_by_id(context.task_id)
                if (task and task.attempt_id == context.attempt_id
                        and task.status not in (TaskStatus.SUBMITTED, TaskStatus.FAILED,
                                                TaskStatus.CANCELLED)):
                    task.cancel()
                    await self._finalizer.finalize(task)
            raise
        except Exception as error:
            if context:
                await self._fail_context(context)
            return "PROFILE_REVIEW_REQUIRED" if str(error) == "PROFILE_REVIEW_REQUIRED" else "EXECUTION_FAILED"
        finally:
            record = self.admission.records.get(permit.id)
            if unknown:
                self.drain.hold_unknown_claim(permit, record)
            elif proof is not None:
                self.budget.release(permit, proof)
            elif context is not None:
                await settle_owned(self.drain.finish(permit, context))
            elif record is not None:
                self.drain.hold_unknown_claim(permit, record)
            else:
                self.budget.release(permit, self.admission.unused(permit))
            self.admission.forget(permit)
            if context and not gate.closed and not asyncio.current_task().cancelling():
                await asyncio.sleep(random.uniform(job.delay_min, job.delay_max))

    async def shutdown(self):
        self.budget.close()
        for gate in tuple(self._gates.values()):
            gate.close()
        await self.drain.shutdown()
