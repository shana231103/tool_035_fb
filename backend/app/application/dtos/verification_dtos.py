# File: backend/app/application/dtos/verification_dtos.py
from datetime import datetime
import re
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.domain.exceptions.mailbox_errors import SAFE_MAILBOX_REASONS


class VerificationSessionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: UUID
    challenge_id: UUID


def safe_verification_metadata(metadata: dict) -> dict:
    result = {}
    for key in ("attempt_id", "challenge_id"):
        try:
            result[key] = str(UUID(str(metadata[key])))
        except (KeyError, ValueError, TypeError):
            continue
    for key in ("requested_at", "expires_at", "deadline"):
        value = metadata.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo:
                    result[key] = parsed.isoformat()
            except ValueError:
                continue
    masked = metadata.get("masked_email")
    if isinstance(masked, str) and re.fullmatch(r"[^@\s]{1}\*{3}@[-a-zA-Z0-9.]+", masked):
        result["masked_email"] = masked
    if metadata.get("mode") == "MICROSOFT_GRAPH":
        result["mode"] = "MICROSOFT_GRAPH"
    if metadata.get("phase") in {"WAITING_MAIL", "VERIFYING", "VERIFIED", "FAILED", "BASELINE", "POLLING"}:
        result["phase"] = metadata["phase"]
    for key in ("attempts", "resends"):
        value = metadata.get(key)
        if type(value) is int and 0 <= value <= 100:
            result[key] = value
    if type(metadata.get("resend_supported")) is bool:
        result["resend_supported"] = metadata["resend_supported"]
    if metadata.get("last_error_code") in SAFE_MAILBOX_REASONS:
        result["last_error_code"] = metadata["last_error_code"]
    return result
