# File: backend/app/application/bulk_order_import.py
from app.application.bulk_import_models import BulkImportError, BulkOrderRow, BulkRowError
from app.application.bulk_url_line import trim_bulk_line, validate_bulk_url_line
from app.domain.exceptions.domain_exceptions import DomainError
from app.domain.value_objects.enums import PlatformType
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


def parse_bulk_orders(text: str, *, max_bytes=2097152, max_orders=1000):
    try:
        size = len(text.encode("utf-8"))
    except (UnicodeError, AttributeError):
        raise BulkImportError("ORDER_FORMAT_INVALID") from None
    if size > max_bytes:
        raise BulkImportError("IMPORT_LIMIT_EXCEEDED", status_code=413)
    lines = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rows, errors, seen = [], [], set()
    current, original, targets, stage = None, None, [], None

    def finish():
        if current is None:
            return
        if original is None or stage != "targets" or not targets:
            errors.append(BulkRowError(current, "ORDER_FORMAT_INVALID"))
            return
        if len(targets) > 30:
            errors.append(BulkRowError(current, "TOO_MANY_TARGETS"))
            return
        identity = (original, tuple(targets))
        if identity in seen:
            errors.append(BulkRowError(current, "DUPLICATE_ORDER"))
        seen.add(identity)
        rows.append(BulkOrderRow(len(rows) + 1, current, original, tuple(targets)))

    blocks = 0
    for number, raw in enumerate(lines, 1):
        if "\ufeff" in raw:
            errors.append(BulkRowError(number, "ORDER_FORMAT_INVALID"))
            continue
        value = trim_bulk_line(raw)
        if not value:
            continue
        label = value.casefold()
        if label == "tên website":
            finish()
            blocks += 1
            if blocks > max_orders:
                raise BulkImportError("IMPORT_LIMIT_EXCEEDED")
            current, original, targets, stage = number, None, [], "original"
            continue
        if label == "website đã fake bài":
            if stage != "label" or original is None:
                errors.append(BulkRowError(number, "ORDER_FORMAT_INVALID"))
            else:
                stage = "targets"
            continue
        try:
            if stage == "original":
                validate_bulk_url_line(raw)
                original = OriginalUrl.from_raw_url(value).url
                stage = "label"
            elif stage == "targets":
                validate_bulk_url_line(raw)
                target = TargetUrl.from_raw_url(value)
                if target.platform != PlatformType.FACEBOOK:
                    raise ValueError("unsupported")
                targets.append(target.url)
            else:
                errors.append(BulkRowError(number, "ORDER_FORMAT_INVALID"))
        except (ValueError, DomainError):
            errors.append(BulkRowError(number, "ORDER_URL_INVALID"))
    finish()
    if not rows and not errors:
        errors.append(BulkRowError(1, "ORDER_FORMAT_INVALID"))
    if errors:
        raise BulkImportError("ORDER_FORMAT_INVALID", errors=errors)
    return tuple(rows)
