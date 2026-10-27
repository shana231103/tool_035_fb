# File: backend/app/application/dispatch_admission.py
import asyncio
from types import MappingProxyType
from uuid import uuid4

from app.application.bulk_import_review import profile_sha256, profile_submission_snapshot
from app.application.dispatch_claim import restore_unstarted, settle_owned
from app.application.execution_context import (
    AdmittedExecution, AdmissionOutcomeUnknown, UnusedPermitConfirmed,
)
from app.domain.value_objects.bulk_import import AttemptClaim
from app.domain.value_objects.enums import JobStatus, TaskStatus
from app.domain.value_objects.explanation import ExplanationText


class DispatchAdmission:
    def __init__(self, factory, connections, sessions, finalizer, browser=None):
        self.factory, self.connections, self.sessions = factory, connections, sessions
        self.finalizer, self.browser = finalizer, browser
        self.records = {}
        self._proofs = {}

    def unused(self, permit, state="NOT_APPLIED"):
        if permit.id in self._proofs:
            return self._proofs[permit.id]
        return UnusedPermitConfirmed(permit.id, permit.task_id, permit.budget_incarnation, state)

    async def _undo(self, permit, record, *, applied):
        context, claim = record
        await self.sessions.unregister(str(context.task_id), context.attempt_id)
        if applied:
            await restore_unstarted(self.factory, claim)
        self.records.pop(permit.id, None)
        proof = self.unused(permit, "RESTORED_UNSTARTED" if applied else "NOT_APPLIED")
        self._proofs[permit.id] = proof
        return proof

    async def prepare(self, task_id, gate, permit, proxy=None):
        if gate.closed:
            return self.unused(permit)
        async with self.factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            job = await uow.jobs.get_by_id(gate.job_id)
            profile = await uow.profiles.get_by_id(job.owner_profile_id) if job else None
        if (not job or job.status != JobStatus.RUNNING or not task or
                task.status != TaskStatus.QUEUED or task.has_submission_evidence or gate.closed):
            return self.unused(permit)
        if not profile:
            raise ValueError("PROFILE_REVIEW_REQUIRED")
        snapshot = profile_submission_snapshot(profile)
        if job.bulk and (not task.assignment or
                         profile_sha256(snapshot) != job.bulk.accepted_profile_sha256):
            raise ValueError("PROFILE_REVIEW_REQUIRED")
        if not job.bulk and task.assignment:
            raise ValueError("IMPORT_METADATA_INVALID")
        email = task.assignment.assigned_mail_email if job.bulk else profile.email.value.casefold()
        if email != permit.email:
            raise ValueError("STALE_REVIEW")
        binding = await self.connections.resolve_binding(email)
        await self.connections.assert_ready(binding)
        if self.browser:
            await self.browser.assert_task_retriable(task.id)
        if gate.closed:
            return self.unused(permit)
        text = " ".join(task.explanation.content.split())
        if len(text) > ExplanationText.MAX_LENGTH:
            text = ExplanationText.create_standard_dmca(task.target_content_type).content
        inputs = dict(owner_name=snapshot.owner_name, sender_name=snapshot.sender_name,
                      owner_email=email, rights_jurisdiction=snapshot.rights_jurisdiction,
                      owner_role=snapshot.owner_role.value, target_url=task.target_url.url,
                      original_url=task.original_url.url, explanation=text)
        attempt = str(uuid4())
        claim = AttemptClaim(task.id, job.id, task.dispatch_revision, task.attempt_id,
                             attempt, inputs, job.bulk.revision if job.bulk else None, snapshot,
                             job.bulk.accepted_profile_sha256 if job.bulk else None,
                             None if job.bulk else email)
        context = AdmittedExecution(task.id, attempt, task.dispatch_revision + 1, snapshot,
                                    email, binding, MappingProxyType(inputs), gate)
        record = (context, claim)
        self.records[permit.id] = record
        applied = False
        try:
            self.sessions.register(str(task.id), attempt, binding, asyncio.current_task())
            await self.sessions.assert_current(str(task.id), attempt, binding)
            task.mark_running(proxy_id=proxy.id if proxy else None)
            task.attempt_id, task.input_snapshot, task.verification = attempt, inputs, {}
            applied, cancelled = await settle_owned(
                self.finalizer.begin_attempt(task, claim.expected_previous_attempt_id, claim=claim))
            if not applied or cancelled or gate.closed:
                result, _ = await settle_owned(self._undo(permit, record, applied=applied))
                return result
            await self.sessions.assert_current(str(task.id), attempt, binding)
            return context
        except BaseException as error:
            # A failed/ambiguous claim may have committed. Never infer rollback from cancellation.
            try:
                async with self.factory() as uow:
                    current = await uow.tasks.get_by_id(task.id)
                if (current and current.attempt_id == attempt
                        and current.dispatch_revision == claim.expected_dispatch_revision + 1):
                    applied = True
                elif (current is None or current.attempt_id != claim.expected_previous_attempt_id
                      or current.dispatch_revision != claim.expected_dispatch_revision):
                    raise AdmissionOutcomeUnknown(task.id, attempt)
                await settle_owned(self._undo(permit, record, applied=applied))
            except BaseException:
                raise AdmissionOutcomeUnknown(task.id, attempt) from None
            if isinstance(error, asyncio.CancelledError):
                return self.unused(permit, "RESTORED_UNSTARTED" if applied else "NOT_APPLIED")
            raise

    def forget(self, permit):
        self.records.pop(permit.id, None)
        self._proofs.pop(permit.id, None)
