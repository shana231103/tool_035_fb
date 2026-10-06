# File: backend/app/infrastructure/mail/mailbox_registry.py
from dataclasses import dataclass

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import MailboxBinding, MailboxConnectionView


def mask_email(email):
    local, _, domain = email.partition("@")
    return (local[:1] + "***@" + domain) if domain else ""


@dataclass(repr=False)
class MailboxRecord:
    id: str
    status: str = "pending"
    primary_email: str = ""
    account_id: str = ""
    generation: int = 1
    revision: int = 0
    mapping: object | None = None
    expires_at: object | None = None
    reason: str | None = None
    cleanup_complete: bool = False
    initializing: bool = False


class MailboxRegistry:
    def __init__(self, *, mapping_busy=None, evidence_versions=(), verified_aliases=None,
                 max_records=100, terminal_history=20):
        if max_records < 1 or not 0 <= terminal_history <= max_records:
            raise ValueError("Invalid mailbox retention limits")
        self.records = {}
        self.max_records, self.terminal_history = max_records, terminal_history
        self.operation_busy = lambda _: False
        self.mapping_busy = mapping_busy or (lambda _: False)
        self.evidence_versions = frozenset(evidence_versions)
        self.verified_aliases = verified_aliases or {}

    def prune(self, *, reserve=False):
        eligible = [key for key, record in self.records.items()
                    if record.status == "error" and record.cleanup_complete and not record.mapping
                    and not self.mapping_busy(key) and not self.operation_busy(key)]
        keep = min(self.terminal_history, self.max_records - 1) if reserve else self.terminal_history
        remove = max(0, len(eligible) - keep)
        if reserve:
            remove = max(remove, len(self.records) - self.max_records + 1)
        for key in eligible[:remove]:
            self.records.pop(key)

    def reserve(self, connection_id):
        self.prune(reserve=True)
        if len(self.records) >= self.max_records:
            raise MailboxError("BUSY")
        record = MailboxRecord(connection_id, initializing=True)
        self.records[connection_id] = record
        return record

    def get(self, connection_id):
        record = self.records.get(connection_id)
        if record is None:
            raise MailboxError("DISCONNECTED")
        return record

    def view(self, record):
        return MailboxConnectionView(record.id, record.status, mask_email(record.primary_email),
                                     mask_email(record.mapping.meta_email) if record.mapping else None,
                                     record.expires_at, record.reason)

    def binding(self, record):
        if record.status != "connected" or record.mapping is None:
            raise MailboxError("AUTH_REQUIRED" if record.status != "connected" else "MAPPING_INVALID")
        mapping = record.mapping
        return MailboxBinding(record.id, record.generation, record.revision, mapping.meta_email,
                              mapping.folders, mapping.template_version)

    def assert_current(self, binding):
        record = self.get(binding.connection_id)
        if record.status != "connected" or record.generation != binding.generation:
            raise MailboxError("DISCONNECTED")
        if self.binding(record) != binding:
            raise MailboxError("STALE")
        if binding.template_version not in self.evidence_versions:
            raise MailboxError("EVIDENCE_REQUIRED")

    def set_mapping(self, connection_id, mapping):
        record = self.get(connection_id)
        if self.mapping_busy(connection_id):
            raise MailboxError("BUSY")
        if record.status != "connected":
            raise MailboxError("AUTH_REQUIRED")
        if mapping.template_version not in self.evidence_versions:
            raise MailboxError("EVIDENCE_REQUIRED")
        allowed = self.verified_aliases.get(record.account_id, ())
        if (mapping.primary_email != record.primary_email or
                any(alias not in allowed for alias in mapping.confirmed_aliases)):
            raise MailboxError("MAPPING_INVALID")
        for other in self.records.values():
            if other.id != connection_id and other.mapping and other.mapping.meta_email == mapping.meta_email:
                raise MailboxError("MAPPING_INVALID")
        record.mapping, record.revision = mapping, record.revision + 1
        return self.binding(record)

    def revoke(self, connection_id):
        record = self.get(connection_id)
        record.cleanup_complete = False
        record.generation += 1
        record.status, record.reason = "disconnecting", "DISCONNECTED"
