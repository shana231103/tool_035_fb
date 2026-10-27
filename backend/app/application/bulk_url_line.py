# File: backend/app/application/bulk_url_line.py
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit

EDGE_WHITESPACE = "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


def trim_bulk_line(value: str) -> str:
    return value.strip(EDGE_WHITESPACE)


def _numeric_host_valid(labels: list[str]) -> bool:
    """Match native IPv4 authority rules, retaining existing public IP variants."""
    if not re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]*)", labels[-1]):
        return True
    if len(labels) > 4:
        return False
    numbers = []
    try:
        for label in labels:
            if label.lower().startswith("0x"):
                numbers.append(int(label[2:] or "0", 16))
            elif len(label) > 1 and label.startswith("0"):
                numbers.append(int(label, 8))
            else:
                numbers.append(int(label, 10))
    except ValueError:
        return False
    return all(number <= 255 for number in numbers[:-1]) and numbers[-1] < 256 ** (5 - len(numbers))


def _hostname_valid(host: str) -> bool:
    if ":" in host:
        try:
            return isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
        except ValueError:
            return False
    try:
        ascii_host = host.encode("idna").decode("ascii").removesuffix(".")
    except UnicodeError:
        return False
    if not ascii_host or len(ascii_host) > 253:
        return False
    labels = ascii_host.split(".")
    return (all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in labels) and _numeric_host_valid(labels))


def _valid_authority(authority: str) -> bool:
    if any(char in authority for char in '@%\\<>^`{}"=,;|'):
        return False
    if authority.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\](?::([0-9]+))?", authority)
        if not match or ":" not in match[1]:
            return False
        host, port = match[1], match[2]
    else:
        match = re.fullmatch(r"([^:]+)(?::([0-9]+))?", authority)
        if not match:
            return False
        host, port = match[1], match[2]
    significant_port = port.lstrip("0") or "0" if port is not None else None
    return _hostname_valid(host) and (significant_port is None
        or len(significant_port) <= 5 and int(significant_port) <= 65535)


def _looks_like_url_start(value: str, start: int = 0) -> bool:
    if re.compile(r"(?:https?://|//)", re.IGNORECASE).match(value, start):
        return True
    token = re.compile(r"[^/\?#,;|]{0,301}").match(value, start)
    authority = token[0]
    if len(authority) > 300:
        return False
    host = authority.split(":", 1)[0]
    qualified = "." in host and any(char.isalpha() for char in host)
    if not qualified and re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", host):
        try:
            qualified = isinstance(ipaddress.ip_address(host), ipaddress.IPv4Address)
        except ValueError:
            qualified = False
    return qualified and _valid_authority(authority)


def _has_ambiguous_list_boundary(value: str) -> bool:
    return any(_looks_like_url_start(value, match.end()) for match in re.finditer(r"[,;|]", value))


def validate_bulk_url_line(value: str) -> None:
    """Check a raw bulk URL line without returning or rewriting its URL."""
    if not isinstance(value, str) or any(unicodedata.category(c) == "Cf" for c in value):
        raise ValueError("ORDER_URL_INVALID")
    clean = trim_bulk_line(value)
    if (not clean or any(c.isspace() or unicodedata.category(c) in {"Cc", "Cf"} for c in clean)
            or "\\" in clean or clean.startswith("//") or _has_ambiguous_list_boundary(clean)):
        raise ValueError("ORDER_URL_INVALID")
    scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", clean)
    if scheme and "." not in scheme[1] and scheme[1].lower() not in {"http", "https"}:
        raise ValueError("ORDER_URL_INVALID")
    candidate = clean if re.match(r"(?i)^https?://", clean) else "https://" + clean
    try:
        parsed = urlsplit(candidate)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or not _valid_authority(parsed.netloc)):
            raise ValueError("ORDER_URL_INVALID")
        parsed.port  # Force stdlib's malformed/out-of-range port validation.
    except ValueError:
        raise ValueError("ORDER_URL_INVALID") from None
