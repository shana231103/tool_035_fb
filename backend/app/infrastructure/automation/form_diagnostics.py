"""Finite pre-submission diagnostics; provider messages and field values are never used."""
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
from .form_selectors import FormContractError

STAGES = {
    "prepare", "copyright", "platform", "jurisdiction_open", "jurisdiction_list", "jurisdiction_option",
    "jurisdiction_retention", "owner_role", "owner_name", "target", "original", "explanation", "sender",
    "email", "confirm_email", "signature", "court_order", "validation", "field",
    *(f"page{page}_{step}" for page in (1, 2, 3, 4) for step in ("validation", "next", "transition")),
}
REASONS = {
    "MISSING": "required control missing", "AMBIGUOUS": "multiple matching controls",
    "DISABLED": "required control disabled", "VALIDATION": "form validation failed",
    "MISSING_VALUE": "required value missing", "NOT_RETAINED": "selection or field value not retained",
    "OWNER_REQUIRED": "confirmed rights owner required", "UNSUPPORTED": "unsupported form choice",
    "TIMEOUT": "control interaction timed out", "PROVIDER": "browser interaction failed",
    "CONTRACT": "form contract mismatch", "UNEXPECTED": "unexpected setup failure",
}


def normalize_stage(stage) -> str:
    return stage if isinstance(stage, str) and stage in STAGES else "prepare"


def safe_form_failure(error: Exception, stage: str = "prepare") -> str:
    """Return display/log-safe text from allowlisted stage, reason and exception category."""
    failure_stage = getattr(error, "stage", None)
    stage = normalize_stage(failure_stage if isinstance(failure_stage, str) and failure_stage in STAGES else stage)
    if isinstance(error, FormContractError):
        supplied = getattr(error, "reason", None)
        reason = supplied if isinstance(supplied, str) and supplied in REASONS else "CONTRACT"
    elif isinstance(error, (PlaywrightTimeout, TimeoutError)):
        reason = "TIMEOUT"
    elif isinstance(error, PlaywrightError):
        reason = "PROVIDER"
    else:
        reason = "UNEXPECTED"
    return f"Form setup failed at {stage.replace('_', ' ')}: {REASONS[reason]} (FORM_{stage.upper()}_{reason})."
