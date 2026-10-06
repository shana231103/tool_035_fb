# File: backend/app/domain/value_objects/mailbox_verification.py
from dataclasses import dataclass, field, replace
from datetime import datetime
import time
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.exceptions.domain_exceptions import InvalidEmailError
from app.domain.value_objects.email_address import EmailAddress


def normalize_email(value: str) -> str:
    try:
        return EmailAddress.from_string(value.strip()).value.casefold()
    except (InvalidEmailError, AttributeError):
        raise MailboxError("MAPPING_INVALID") from None


@dataclass(frozen=True)
class MailboxMapping:
    meta_email: str
    primary_email: str
    confirmed_aliases: tuple[str, ...] = ()
    folders: tuple[str, ...] = ("inbox",)
    template_version: str = ""

    def __post_init__(self):
        object.__setattr__(self, "meta_email", normalize_email(self.meta_email))
        object.__setattr__(self, "primary_email", normalize_email(self.primary_email))
        aliases = tuple(normalize_email(a) for a in self.confirmed_aliases)
        object.__setattr__(self, "confirmed_aliases", aliases)
        if (self.meta_email not in (self.primary_email, *aliases) or
                not self.folders or len(set(self.folders)) != len(self.folders) or
                any(f not in ("inbox", "junkemail") for f in self.folders) or
                not self.template_version.strip()):
            raise MailboxError("MAPPING_INVALID")


@dataclass(frozen=True)
class MailboxBinding:
    connection_id: str
    generation: int
    mapping_revision: int
    meta_email: str
    folder_refs: tuple[str, ...]
    template_version: str

    def __post_init__(self):
        if self.generation <= 0 or self.mapping_revision <= 0:
            raise MailboxError("MAPPING_INVALID")


@dataclass(frozen=True, repr=False)
class DeviceLoginPrompt:
    login_id: str
    verification_uri: str
    user_code: str
    expires_at: datetime
    interval_seconds: int


@dataclass(frozen=True)
class MailboxConnectionView:
    id: str
    status: str
    masked_email: str = ""
    mapped_email_masked: str | None = None
    expires_at: datetime | None = None
    safe_reason: str | None = None


@dataclass(frozen=True)
class MailBaseline:
    ids: frozenset[str]
    captured_at: datetime
    complete: bool


@dataclass(frozen=True)
class PreparedSend:
    task_id: str
    attempt_id: str
    binding: MailboxBinding
    baseline: MailBaseline
    deadline: float
    request_started_at: datetime | None = None


def stamp_dispatch(prepared: PreparedSend, utc_now: datetime) -> PreparedSend:
    if utc_now.tzinfo is None or utc_now.utcoffset() is None:
        raise MailboxError("GRAPH_PROTOCOL_ERROR")
    return replace(prepared, request_started_at=utc_now)


@dataclass(frozen=True)
class SendEpoch:
    epoch_id: str
    task_id: str
    attempt_id: str
    binding: MailboxBinding
    request_started_at: datetime
    baseline_ids: frozenset[str]
    deadline: float
    observed_request_id: str | None = None


@dataclass(frozen=True)
class MessageRef:
    id: str
    internet_message_id: str | None
    received_at: datetime
    recipient_match: bool
    template_match: bool


@dataclass(frozen=True, repr=False)
class CodeCandidate:
    message_ref: MessageRef
    code: str
    template_version: str
    provider_request_id: str | None = None


@dataclass(frozen=True)
class CorrelationVerdict:
    outcome: str
    safe_reason: str
    message_ref: MessageRef | None = None


@dataclass(frozen=True)
class CandidatePage:
    refs: tuple[MessageRef, ...]
    next_cursor: str | None = None
    complete: bool = True


@dataclass
class ReadBudget:
    request_remaining: int
    page_remaining: int
    body_remaining: int
    deadline: float
    clock: object = field(default=time.monotonic, repr=False)

    def check(self) -> None:
        if self.clock() >= self.deadline:
            raise MailboxError("READ_BUDGET_EXHAUSTED")

    def consume_request(self) -> None:
        self.check()
        if self.request_remaining <= 0:
            raise MailboxError("READ_BUDGET_EXHAUSTED")
        self.request_remaining -= 1

    def consume_page(self) -> None:
        if self.page_remaining <= 0:
            raise MailboxError("READ_BUDGET_EXHAUSTED")
        self.page_remaining -= 1

    def consume_body(self) -> None:
        if self.body_remaining <= 0:
            raise MailboxError("READ_BUDGET_EXHAUSTED")
        self.body_remaining -= 1


@dataclass
class AttemptMailLedger:
    send_epochs: list[SendEpoch] = field(default_factory=list)
    attempted_ids: set[str] = field(default_factory=set)
    consumed_ids: set[str] = field(default_factory=set)
    attempted_code_digests: set[bytes] = field(default_factory=set, repr=False)
    digest_key: bytes = field(default=b"", repr=False)


@dataclass
class AttemptReadContext:
    task_id: str
    attempt_id: str
    budget: ReadBudget
    ledger: AttemptMailLedger
    active_epoch_id: str | None = None
