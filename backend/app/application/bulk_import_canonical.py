# File: backend/app/application/bulk_import_canonical.py
from dataclasses import asdict
from enum import Enum
import hashlib
import json
from uuid import UUID
from app.application.bulk_import_models import BulkImportError
from app.application.bulk_order_import import parse_bulk_orders
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.mailbox_verification import normalize_email


def digest(value):
    def encode(item):
        if isinstance(item, (UUID, Enum)):
            return str(item.value if isinstance(item, Enum) else item)
        if hasattr(item, "isoformat"):
            return item.isoformat()
        raise TypeError("Unsupported canonical value")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         default=encode).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalized_settings(preview):
    name = preview.name.strip()
    if not name or len(name) > 255:
        raise BulkImportError("ORDER_FORMAT_INVALID")
    explanation = preview.custom_explanation
    if explanation is not None:
        if not explanation.strip():
            raise BulkImportError("ORDER_FORMAT_INVALID")
        explanation = ExplanationText.custom(explanation).content
    return name, explanation


def canonical_pool(refs):
    if not 1 <= len(refs) <= 100:
        raise BulkImportError("IMPORT_LIMIT_EXCEEDED")
    emails, previous_line = [], 0
    for ref in refs:
        try:
            email = normalize_email(ref.expected_email)
        except MailboxError:
            raise BulkImportError("MAIL_ROW_INVALID") from None
        if ref.source_line <= previous_line or email in emails:
            raise BulkImportError("MAIL_DUPLICATE")
        previous_line = ref.source_line
        emails.append(email)
    return tuple(emails)


def canonical_request_sha256(command):
    preview = command.preview
    name, explanation = normalized_settings(preview)
    rows = parse_bulk_orders(preview.orders_text)
    return digest({"version": "bulk-request-v1", "name": name, "profile_id": preview.profile_id,
                   "profile_sha256": command.expected_profile_sha256,
                   "rows": [{"original_url": r.original_url, "target_urls": r.target_urls} for r in rows],
                   "mail_pool": canonical_pool(preview.mailboxes),
                   "preferred_country": preview.preferred_country, "explanation": explanation})


def canonical_content_sha256(profile_id, rows, explanation):
    return digest({"version": "bulk-content-v1", "profile_id": profile_id,
                   "rows": [{"original_url": r.original_url, "target_urls": r.target_urls} for r in rows],
                   "explanation": explanation})


def duplicate_ack_sha256(content, matches):
    if not matches:
        return None
    values = [asdict(match) for match in matches]
    return digest({"version": "bulk-ack-v1", "content": content,
                   "matches": sorted(values, key=lambda m: str(m["job_id"]))})


def binding_value(binding):
    return {"connection_id": str(binding.connection_id), "generation": binding.generation,
            "mapping_revision": binding.mapping_revision, "email": normalize_email(binding.meta_email),
            "template": binding.template_version}


async def validate_mail_pool(refs, connections):
    emails = canonical_pool(refs)
    if len({str(ref.connection_id) for ref in refs}) != len(refs):
        raise BulkImportError("MAIL_DUPLICATE")
    bindings = []
    for ref, email in zip(refs, emails):
        try:
            binding = await connections.resolve_binding(email)
            await connections.assert_ready(binding)
        except MailboxError:
            raise BulkImportError("MAIL_UNAVAILABLE", status_code=409) from None
        if str(binding.connection_id) != str(ref.connection_id) or normalize_email(binding.meta_email) != email:
            raise BulkImportError("MAIL_ROW_INVALID", status_code=409)
        bindings.append(binding)
    return tuple(bindings)


def preview_digest(request_hash, profile_hash, bindings):
    return digest({"version": "bulk-preview-v1", "request": request_hash, "profile": profile_hash,
                   "bindings": [binding_value(binding) for binding in bindings]})


def mask_email(email):
    local, domain = email.split("@", 1)
    return local[:1] + "***@" + domain
