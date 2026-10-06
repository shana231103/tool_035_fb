# File: backend/app/application/mailbox_correlation.py
import hashlib
import hmac
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import (
    AttemptMailLedger, CodeCandidate, CorrelationVerdict, SendEpoch,
)


class MailboxCorrelationPolicy:
    """Explicit provider-ID or fresh-unique modes; neither is enabled by default.

    Fresh delivery cannot prove which request sent mail when an external request
    overlaps or an older request's delivery is delayed. Never invent an ID.
    """
    FRESH_VERSIONS = frozenset({"meta-report-email-v1"})

    def __init__(self, certified_versions: tuple[str, ...] = (), *, allow_test: bool = False,
                 fresh_versions: tuple[str, ...] = ()):
        if any(v.startswith("synthetic-") for v in certified_versions) and not allow_test:
            raise MailboxError("EVIDENCE_REQUIRED")
        self._versions = frozenset(certified_versions)
        self._fresh_versions = frozenset(fresh_versions)
        if (not self._fresh_versions <= self.FRESH_VERSIONS or
                self._fresh_versions & self._versions):
            raise MailboxError("EVIDENCE_REQUIRED")

    def assert_supported(self, version: str) -> None:
        if version not in self._versions | self._fresh_versions:
            raise MailboxError("EVIDENCE_REQUIRED")

    def requires_request_id(self, version: str) -> bool:
        self.assert_supported(version)
        return version not in self._fresh_versions

    def can_resend(self, version: str) -> bool:
        return self.requires_request_id(version)

    @staticmethod
    def digest(ledger: AttemptMailLedger, code: str) -> bytes:
        return hmac.new(ledger.digest_key, code.encode("ascii"), hashlib.sha256).digest()

    def decide(self, epoch: SendEpoch, candidate: CodeCandidate,
               ledger: AttemptMailLedger) -> CorrelationVerdict:
        ref = candidate.message_ref
        def verdict(outcome, reason):
            return CorrelationVerdict(outcome, reason, ref)
        if (ref.id in epoch.baseline_ids or ref.id in ledger.attempted_ids or
                not ref.recipient_match or not ref.template_match or
                ref.received_at < epoch.request_started_at or
                candidate.template_version != epoch.binding.template_version):
            return verdict("rejected", "CORRELATION_UNRESOLVED")
        if not (candidate.code.isascii() and candidate.code.isdigit() and 4 <= len(candidate.code) <= 12):
            return verdict("rejected", "CORRELATION_UNRESOLVED")
        if self.digest(ledger, candidate.code) in ledger.attempted_code_digests:
            return verdict("rejected", "CODE_REPLAY")
        if candidate.template_version in self._fresh_versions:
            if (epoch.observed_request_id is not None or candidate.provider_request_id is not None or
                    len(ledger.send_epochs) != 1 or ledger.send_epochs[0] != epoch):
                return verdict("unresolved", "CORRELATION_UNRESOLVED")
            return verdict("confirmed", "VERIFICATION_FAILED")
        if (candidate.template_version not in self._versions or not epoch.observed_request_id
                or not candidate.provider_request_id):
            return verdict("unresolved", "CORRELATION_UNRESOLVED")
        if candidate.provider_request_id != epoch.observed_request_id:
            return verdict("rejected", "CORRELATION_UNRESOLVED")
        if any(old.epoch_id != epoch.epoch_id and
               old.observed_request_id == candidate.provider_request_id for old in ledger.send_epochs):
            return verdict("ambiguous", "CORRELATION_AMBIGUOUS")
        return verdict("confirmed", "VERIFICATION_FAILED")

    def record_attempted(self, ledger: AttemptMailLedger, candidate: CodeCandidate) -> None:
        ledger.attempted_ids.add(candidate.message_ref.id)
        ledger.attempted_code_digests.add(self.digest(ledger, candidate.code))
