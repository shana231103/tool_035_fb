# File: backend/app/application/task_preparation.py
"""Validate and freeze all report inputs before any provider acquisition."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from app.application.task_diagnostics import TaskAttemptTrace, TaskStage

from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.value_objects.enums import PlatformType, TaskStatus
from app.domain.value_objects.mailbox_verification import MailboxBinding
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.operator_identity import ValidatedProxyEndpoint
from app.domain.value_objects.report_targets import ReportTargets
from app.domain.value_objects.task_execution import ExecutionGrant


@dataclass(frozen=True)
class PreparedAttempt:
    grant: ExecutionGrant
    profile_id: UUID
    target_urls: tuple[str, ...]
    original_url: str
    explanation: str
    owner_name: str
    sender_name: str
    owner_email: str
    rights_jurisdiction: str
    owner_role: str
    mailbox_binding: MailboxBinding
    prepared_at: datetime
    deadline: float
    input_digest: str
    infringing_account: str | None = None
    proxy_id: UUID | None = None
    proxy_server: str | None = field(default=None, repr=False)
    proxy_username: str | None = field(default=None, repr=False)
    proxy_password: str | None = field(default=None, repr=False)
    validated_proxy: ValidatedProxyEndpoint | None = field(default=None, repr=False)

    def snapshot(self):
        return {"target_urls": self.target_urls, "original_url": self.original_url,
                "explanation": self.explanation, "owner_name": self.owner_name,
                "sender_name": self.sender_name, "owner_email": self.owner_email,
                "rights_jurisdiction": self.rights_jurisdiction, "owner_role": self.owner_role,
                "input_digest": self.input_digest}


class TaskPreparation:
    def __init__(self, factory, browser, clock, proxy_policy, mailboxes, authority):
        self._factory, self._browser, self._clock = factory, browser, clock
        self._proxy_policy, self._mailboxes, self._authority = proxy_policy, mailboxes, authority

    async def prepare(self, grant, deadline, *, trace: TaskAttemptTrace | None = None):
        trace = trace if trace is not None else TaskAttemptTrace(grant)
        async with self._factory.owned(grant.scope.operator_id) as uow:
            trace.enter(TaskStage.AUTHORITY)
            task = await self._authority.require_run(uow, grant)
            if task.status != TaskStatus.PREPARING:
                raise ValueError("EXECUTION_GRANT_MISMATCH")
            trace.enter(TaskStage.PROFILE)
            profile = await uow.profiles.get_by_id(task.owner_profile_id)
            if profile is None or profile.operator_id != grant.scope.operator_id:
                raise EntityNotFoundError("NOT_FOUND")
            profile.validate_for_submission()
            trace.enter(TaskStage.INPUTS)
            targets = ReportTargets.from_urls(task.targets.urls)
            if any(item.platform != PlatformType.FACEBOOK for item in targets.items):
                raise ValueError("INPUT_INVALID")
            original = OriginalUrl.from_raw_url(task.original_url.url)
            explanation = " ".join(task.explanation.content.split())
            if not explanation:
                raise ValueError("INPUT_INVALID")
            trace.enter(TaskStage.PROXY_SELECT)
            proxy = await uow.proxies.get_by_id(task.proxy_id) if task.proxy_id else None
            if proxy is None and task.preferred_country:
                proxy = await uow.proxies.get_active_proxy(task.preferred_country)
            if proxy and proxy.operator_id != grant.scope.operator_id:
                raise EntityNotFoundError("NOT_FOUND")
            inputs = dict(target_urls=targets.urls, original_url=original.url,
                explanation=explanation, owner_name=profile.rights_owner_name.strip(),
                sender_name=profile.sender_name.strip(), owner_email=profile.email.value,
                rights_jurisdiction=profile.rights_jurisdiction, owner_role=profile.owner_role.value)
            profile_id = profile.id
            trace.enter(TaskStage.READ_SCOPE_EXIT)
        trace.enter(TaskStage.PREPARATION_BUDGET)
        if self._clock.monotonic() >= deadline:
            raise TimeoutError("PREPARATION_TIMEOUT")
        trace.enter(TaskStage.PROXY_VALIDATE)
        endpoint = await self._proxy_policy.prepare(proxy, deadline) if proxy else None
        trace.enter(TaskStage.MAILBOX_BINDING)
        binding = await self._mailboxes.resolve_binding(inputs["owner_email"], owner=grant.scope.operator_id)
        trace.enter(TaskStage.MAILBOX_READY)
        await self._mailboxes.assert_ready(binding)
        trace.enter(TaskStage.BROWSER_READY)
        await self._browser.assert_ready()
        trace.enter(TaskStage.BROWSER_RESOURCES)
        await self._browser.assert_task_retriable(grant.scope.task_id)
        trace.enter(TaskStage.FREEZE_INPUT)
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return PreparedAttempt(grant=grant, profile_id=profile_id, **inputs,
            mailbox_binding=binding, prepared_at=self._clock.now(), deadline=deadline,
            input_digest=digest, infringing_account=targets.extract_account_identifier(),
            proxy_id=proxy.id if proxy else None, validated_proxy=endpoint,
            proxy_server=(f"{endpoint.protocol}://[{endpoint.connect_ip}]:{endpoint.port}"
                          if endpoint and ":" in endpoint.connect_ip else
                          f"{endpoint.protocol}://{endpoint.connect_ip}:{endpoint.port}" if endpoint else None),
            proxy_username=proxy.username if proxy else None, proxy_password=proxy.password if proxy else None)
