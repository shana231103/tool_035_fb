# File: backend/app/domain/value_objects/report_targets.py
"""Immutable domain value object representing validated report target URLs."""

from dataclasses import dataclass
import re
from typing import Sequence, Tuple, Union
from urllib.parse import urlparse

from app.domain.exceptions.domain_exceptions import (
    InvalidMetaUrlError,
    TargetLimitExceededError,
)
from app.domain.value_objects.target_url import TargetUrl


@dataclass(frozen=True)
class ReportTargets:
    items: Tuple[TargetUrl, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        count = len(self.items)
        if count < 1:
            raise InvalidMetaUrlError("Target URL list must contain between 1 and 30 URLs.")
        if count > 30:
            raise TargetLimitExceededError(
                f"Target URL count {count} exceeds the single report limit of 30."
            )

    @classmethod
    def from_urls(
        cls, raw_urls: Sequence[Union[str, TargetUrl]]
    ) -> "ReportTargets":
        if raw_urls is None or len(raw_urls) < 1:
            raise InvalidMetaUrlError("Target URL list must contain between 1 and 30 URLs.")
        if len(raw_urls) > 30:
            raise TargetLimitExceededError(
                f"Target URL count {len(raw_urls)} exceeds the single report limit of 30."
            )

        validated: list[TargetUrl] = []
        for raw in raw_urls:
            if isinstance(raw, TargetUrl):
                url_str = raw.url
            elif isinstance(raw, str):
                url_str = raw.strip()
            else:
                raise InvalidMetaUrlError(f"Unsupported target item type: {type(raw)}")

            if not url_str:
                raise InvalidMetaUrlError("Target URL item cannot be empty.")

            if len(url_str) > 2048:
                raise InvalidMetaUrlError("Target URL exceeds maximum length of 2048 characters.")

            if re.search(r"[\x00-\x1f\x7f]", url_str):
                raise InvalidMetaUrlError("Target URL contains control characters.")

            if re.search(r"\s", url_str):
                raise InvalidMetaUrlError("Target URL contains raw whitespace.")

            if "," in url_str or ";" in url_str:
                raise InvalidMetaUrlError(
                    "Target URL contains unescaped list separator (',' or ';')."
                )

            scheme_url = url_str if re.match(r"^https?://", url_str, re.I) else f"https://{url_str}"
            parsed = urlparse(scheme_url)
            if parsed.username or parsed.password:
                raise InvalidMetaUrlError("Target URL cannot contain userinfo.")

            if isinstance(raw, TargetUrl):
                validated.append(raw)
            else:
                validated.append(TargetUrl.from_raw_url(url_str))

        return cls(items=tuple(validated))

    @property
    def target_count(self) -> int:
        return len(self.items)

    @property
    def urls(self) -> Tuple[str, ...]:
        return tuple(item.url for item in self.items)

    @property
    def content_type(self) -> str:
        types = {item.content_type for item in self.items}
        if len(types) == 1:
            return next(iter(types))
        return "post"

    @property
    def joined_urls(self) -> str:
        return "\n".join(item.url for item in self.items)

    def extract_account_identifier(self) -> Union[str, None]:
        for item in self.items:
            acc = item.extract_account_identifier()
            if acc:
                return acc
        return None
