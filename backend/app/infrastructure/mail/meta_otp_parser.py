# File: backend/app/infrastructure/mail/meta_otp_parser.py
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

from app.domain.value_objects.mailbox_verification import CodeCandidate, MailboxMapping, MessageRef


@dataclass(frozen=True)
class TemplateEvidence:
    version: str
    sender_addresses: tuple[str, ...]
    subject_pattern: str
    code_pattern: str
    code_length: int
    request_id_pattern: str | None = None
    evidence_reference: str = ""

    def __post_init__(self):
        if not self.version or not self.evidence_reference or not self.sender_addresses or not 4 <= self.code_length <= 12:
            raise ValueError("Incomplete template evidence")
        for pattern in (self.subject_pattern, self.code_pattern, self.request_id_pattern):
            if pattern is not None:
                re.compile(pattern)
        object.__setattr__(self, "sender_addresses", tuple(a.casefold() for a in self.sender_addresses))
        if "code" not in re.compile(self.code_pattern).groupindex:
            raise ValueError("Evidence needs an explicit code zone")
        if self.request_id_pattern and "request_id" not in re.compile(self.request_id_pattern).groupindex:
            raise ValueError("Evidence needs an explicit correlation zone")


class _VisibleText(HTMLParser):
    _BLOCKS = frozenset(("p", "div", "br", "tr", "td", "th", "table", "tbody", "li",
                         "h1", "h2", "h3", "h4", "h5", "h6"))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.hidden += 1
        if tag in self._BLOCKS and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.hidden:
            self.hidden -= 1
        if tag in self._BLOCKS and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class MetaOtpParser:
    """No default sender/template assumptions; only explicit evidence is accepted."""

    def __init__(self, profiles=None):
        self.profiles = dict(profiles or {})
        if any(key != profile.version for key, profile in self.profiles.items()):
            raise ValueError("Evidence version mismatch")

    def _template_matches(self, metadata, version):
        profile = self.profiles.get(version)
        if profile is None:
            return False
        addresses = []
        for key in ("from", "sender"):
            sender = metadata.get(key, {})
            if not isinstance(sender, dict) or not isinstance(sender.get("emailAddress", {}), dict):
                return False
            value = sender.get("emailAddress", {}).get("address", "")
            if not isinstance(value, str):
                return False
            if value:
                addresses.append(value.casefold())
        if not isinstance(metadata.get("subject", ""), str):
            return False
        return bool(addresses and all(a in profile.sender_addresses for a in addresses)
                    and re.fullmatch(profile.subject_pattern, metadata.get("subject", "")))

    def metadata_matches(self, metadata: dict, mapping: MailboxMapping) -> bool:
        values = metadata.get("toRecipients", [])
        if not isinstance(values, list):
            return False
        recipients = set()
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("emailAddress"), dict):
                return False
            address = item["emailAddress"].get("address")
            if not isinstance(address, str):
                return False
            recipients.add(address.casefold())
        return mapping.meta_email in recipients and self._template_matches(metadata, mapping.template_version)

    def parse(self, metadata: dict, body: str, body_type: str, template_version: str) -> CodeCandidate | None:
        if (not self._template_matches(metadata, template_version) or not isinstance(body, str)
                or not isinstance(body_type, str) or len(body) > 1_000_000):
            return None
        profile = self.profiles[template_version]
        if body_type.casefold() == "html":
            parser = _VisibleText()
            parser.feed(body)
            text = "".join(parser.parts)
        elif body_type.casefold() == "text":
            text = body
        else:
            return None
        matches = list(re.finditer(profile.code_pattern, text, re.MULTILINE))
        if len(matches) != 1 or "code" not in matches[0].groupdict():
            return None
        code = matches[0].group("code")
        if not re.fullmatch(r"[0-9]{" + str(profile.code_length) + "}", code):
            return None
        request_id = None
        if profile.request_id_pattern:
            request_matches = list(re.finditer(profile.request_id_pattern, text, re.MULTILINE))
            if len(request_matches) != 1 or "request_id" not in request_matches[0].groupdict():
                return None
            request_id = request_matches[0].group("request_id")
        try:
            received = datetime.fromisoformat(metadata["receivedDateTime"].replace("Z", "+00:00"))
            if received.tzinfo is None or not isinstance(metadata["id"], str) or not metadata["id"]:
                return None
            ref = MessageRef(metadata["id"], metadata.get("internetMessageId"), received, False, True)
        except (KeyError, TypeError, ValueError):
            return None
        return CodeCandidate(ref, code, template_version, request_id)
