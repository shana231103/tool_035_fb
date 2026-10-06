# File: backend/app/domain/ports/mailbox_code_reader.py
from abc import ABC, abstractmethod
from app.domain.value_objects.mailbox_verification import (
    MailboxBinding, MailboxMapping, DeviceLoginPrompt, MailboxConnectionView,
    ReadBudget, MailBaseline, SendEpoch, CandidatePage, MessageRef, CodeCandidate,
    PreparedSend,
)


class IMailboxConnections(ABC):
    @abstractmethod
    async def begin_login(self, account_hint: str | None) -> DeviceLoginPrompt:
        raise NotImplementedError

    @abstractmethod
    async def login_status(self, login_id: str) -> MailboxConnectionView:
        raise NotImplementedError

    @abstractmethod
    async def cancel_login(self, login_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_connections(self) -> tuple[MailboxConnectionView, ...]:
        raise NotImplementedError

    @abstractmethod
    async def set_mapping(self, connection_id: str, mapping: MailboxMapping) -> MailboxBinding:
        raise NotImplementedError

    @abstractmethod
    async def resolve_binding(self, email: str) -> MailboxBinding:
        raise NotImplementedError

    @abstractmethod
    async def assert_ready(self, binding: MailboxBinding) -> None:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self, connection_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError


class IMailboxCodeReader(ABC):
    @abstractmethod
    async def baseline(self, binding: MailboxBinding, budget: ReadBudget) -> MailBaseline:
        raise NotImplementedError

    @abstractmethod
    async def list_candidates(self, epoch: SendEpoch, cursor: str | None,
                              budget: ReadBudget) -> CandidatePage:
        raise NotImplementedError

    @abstractmethod
    async def read_candidate(self, binding: MailboxBinding, ref: MessageRef,
                             budget: ReadBudget) -> CodeCandidate | None:
        raise NotImplementedError


class IEmailCodeCollector(ABC):
    @abstractmethod
    async def assert_current(self, epoch: SendEpoch) -> None:
        raise NotImplementedError

    @abstractmethod
    async def prepare_send(self, binding: MailboxBinding, task_id: str, attempt_id: str,
                           deadline: float) -> PreparedSend:
        raise NotImplementedError

    @abstractmethod
    async def mark_dispatched(self, prepared: PreparedSend,
                              observed_request_id: str | None) -> SendEpoch:
        raise NotImplementedError

    @abstractmethod
    async def collect(self, epoch: SendEpoch, challenge_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self, task_id: str, attempt_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def assert_ready(self, binding: MailboxBinding) -> None:
        raise NotImplementedError
