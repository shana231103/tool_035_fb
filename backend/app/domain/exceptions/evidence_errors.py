# File: backend/app/domain/exceptions/evidence_errors.py
from typing import Literal
from app.domain.exceptions.domain_exceptions import DomainError

EvidenceReason = Literal["UNSUPPORTED_IMAGE", "INVALID_IMAGE", "TOO_LARGE", "STORAGE_FAILED"]


class EvidenceFileError(DomainError):
    """Safe evidence failure without client content, paths or decoder details."""

    def __init__(self, reason: EvidenceReason):
        self.reason = reason
        messages = {
            "UNSUPPORTED_IMAGE": "Use a single-frame PNG, JPEG or WebP image.",
            "INVALID_IMAGE": "The evidence image is empty, damaged or invalid.",
            "TOO_LARGE": "The evidence image exceeds the allowed size.",
            "STORAGE_FAILED": "The evidence image could not be stored.",
        }
        super().__init__(messages[reason])
