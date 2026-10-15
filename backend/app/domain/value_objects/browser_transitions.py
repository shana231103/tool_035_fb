# File: backend/app/domain/value_objects/browser_transitions.py
from dataclasses import replace
from datetime import datetime, timezone
from app.domain.exceptions.browser_errors import BrowserLedgerConflict
from app.domain.value_objects.browser_session import (
    BrowserPhase as P, BrowserSessionMutation, BrowserSessionRecord,
    CleanupState, CompletionEvidence as E,
)

NEXT_PHASES = {
    P.RESERVED: {P.CREATE_IN_FLIGHT, P.CLOSED},
    P.CREATE_IN_FLIGHT: {P.PROFILE_CREATED, P.UNKNOWN_CREATE, P.CLOSED},
    P.PROFILE_CREATED: {P.START_IN_FLIGHT, P.ATTACHED, P.RELEASING},
    P.START_IN_FLIGHT: {P.ATTACHED, P.RELEASING, P.CLEANUP_PENDING},
    P.ATTACHED: {P.RELEASING},
    P.RELEASING: {P.STOP_CONFIRMED, P.CLEANUP_PENDING},
    P.STOP_CONFIRMED: {P.DELETE_IN_FLIGHT, P.CLEANUP_PENDING},
    P.DELETE_IN_FLIGHT: {P.CLOSED, P.DELETE_UNKNOWN, P.CLEANUP_PENDING},
    P.UNKNOWN_CREATE: {P.PROFILE_CREATED, P.NEEDS_OPERATOR},
    P.CLEANUP_PENDING: {P.RELEASING, P.STOP_CONFIRMED, P.DELETE_IN_FLIGHT, P.NEEDS_OPERATOR, P.CLOSED},
    P.DELETE_UNKNOWN: {P.RELEASING, P.STOP_CONFIRMED, P.DELETE_IN_FLIGHT, P.NEEDS_OPERATOR, P.CLOSED},
    P.NEEDS_OPERATOR: {P.PROFILE_CREATED, P.RELEASING, P.STOP_CONFIRMED, P.DELETE_IN_FLIGHT, P.CLOSED},
}


def apply_mutation(record: BrowserSessionRecord, mutation: BrowserSessionMutation) -> BrowserSessionRecord:
    def reject():
        raise BrowserLedgerConflict(record.operation_id)
    phase, evidence = mutation.next_phase, mutation.completion_evidence
    if record.phase == P.CLOSED:
        reject()
    external_close = phase == P.CLOSED and evidence == E.EXTERNAL and mutation.audit_reference is not None
    if not external_close and phase != record.phase and phase not in NEXT_PHASES.get(record.phase, set()):
        reject()
    profile = mutation.newly_observed_profile_id or record.profile_id
    if record.profile_id is not None and profile != record.profile_id:
        reject()
    if mutation.newly_observed_profile_id is not None and record.profile_id is None and phase != P.PROFILE_CREATED:
        reject()
    if phase in {P.PROFILE_CREATED, P.START_IN_FLIGHT, P.ATTACHED, P.RELEASING, P.STOP_CONFIRMED, P.DELETE_IN_FLIGHT, P.DELETE_UNKNOWN} and profile is None:
        reject()
    if phase == P.CLOSED:
        if mutation.next_cleanup_state != CleanupState.CONFIRMED or evidence == E.UNKNOWN:
            reject()
        if evidence == E.NOT_CREATED and (record.phase not in {P.RESERVED, P.CREATE_IN_FLIGHT} or profile is not None):
            reject()
        if evidence == E.DELETE_ACK and (profile is None or record.phase not in {P.DELETE_IN_FLIGHT, P.DELETE_UNKNOWN, P.CLEANUP_PENDING, P.NEEDS_OPERATOR}):
            reject()
        if evidence == E.EXTERNAL and not external_close:
            reject()
    elif evidence != E.UNKNOWN or mutation.next_cleanup_state == CleanupState.CONFIRMED:
        reject()
    retries = record.retries if mutation.retry_count is None else mutation.retry_count
    if retries < record.retries:
        reject()
    return replace(record, phase=phase, cleanup_state=mutation.next_cleanup_state, profile_id=profile,
                   charged=phase != P.CLOSED, completion_evidence=evidence,
                   audit_reference=mutation.audit_reference or record.audit_reference,
                   version=record.version + 1, updated_at=datetime.now(timezone.utc),
                   safe_reason=mutation.safe_reason, retries=retries, next_retry_at=mutation.next_retry_at)
