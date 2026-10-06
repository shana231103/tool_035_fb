from dataclasses import dataclass
import ipaddress
import re
from typing import Optional, Union
from urllib.parse import urlparse
from app.domain.exceptions.domain_exceptions import DomainError, InvalidOriginalUrlError


def _try_parse_ip_or_variant(host_str: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    """Attempts to parse standard and alternative/obscure IP representations."""
    # 1. Standard ipaddress parse (standard IPv4, bracketed/unbracketed IPv6)
    try:
        return ipaddress.ip_address(host_str)
    except ValueError:
        pass

    # 2. Integer/Dword representation (e.g. 2130706433)
    if host_str.isdigit():
        try:
            val = int(host_str)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    # 3. Hex representation (e.g. 0x7f000001)
    if (host_str.startswith("0x") or host_str.startswith("0X")) and len(host_str) <= 10:
        try:
            val = int(host_str, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    # 4. Octal, shortened, or mixed dotted IPv4 notation (e.g. 0177.0.0.1, 127.1)
    if "." in host_str:
        parts = host_str.split(".")
        if 1 <= len(parts) <= 4:
            parsed_parts = []
            valid_parts = True
            for part in parts:
                if not part:
                    valid_parts = False
                    break
                try:
                    if part.startswith("0x") or part.startswith("0X"):
                        num = int(part, 16)
                    elif part.startswith("0") and len(part) > 1 and all(c in "01234567" for c in part):
                        num = int(part, 8)
                    elif part.isdigit():
                        num = int(part, 10)
                    else:
                        valid_parts = False
                        break
                    parsed_parts.append(num)
                except ValueError:
                    valid_parts = False
                    break

            if valid_parts:
                try:
                    if len(parsed_parts) == 4:
                        if all(0 <= p <= 255 for p in parsed_parts):
                            val = (parsed_parts[0] << 24) | (parsed_parts[1] << 16) | (parsed_parts[2] << 8) | parsed_parts[3]
                            return ipaddress.IPv4Address(val)
                    elif len(parsed_parts) == 2:
                        if 0 <= parsed_parts[0] <= 255 and 0 <= parsed_parts[1] <= 0xFFFFFF:
                            val = (parsed_parts[0] << 24) | parsed_parts[1]
                            return ipaddress.IPv4Address(val)
                    elif len(parsed_parts) == 3:
                        if 0 <= parsed_parts[0] <= 255 and 0 <= parsed_parts[1] <= 255 and 0 <= parsed_parts[2] <= 0xFFFF:
                            val = (parsed_parts[0] << 24) | (parsed_parts[1] << 16) | parsed_parts[2]
                            return ipaddress.IPv4Address(val)
                except (ValueError, OverflowError):
                    pass

    return None


@dataclass(frozen=True)
class OriginalUrl:
    url: str

    @classmethod
    def from_raw_url(cls, raw_url: str) -> "OriginalUrl":
        clean_url = (raw_url or "").strip()
        if not clean_url:
            raise InvalidOriginalUrlError("Original proof URL cannot be empty.")

        if clean_url.startswith("/"):
            raise InvalidOriginalUrlError(
                "Relative URLs are forbidden for original proof. A fully qualified public domain is required."
            )

        if not re.match(r"^https?://", clean_url, re.IGNORECASE):
            clean_url = "https://" + clean_url

        # Check for unbracketed IPv6 (contains multiple colons without brackets)
        url_no_scheme = re.sub(r"^https?://", "", clean_url, flags=re.IGNORECASE)
        authority = url_no_scheme.split("/")[0].split("?")[0].split("#")[0]
        if "@" in authority:
            authority = authority.split("@")[-1]

        if authority.count(":") >= 2 and not (authority.startswith("[") and "]" in authority):
            try:
                ip = ipaddress.ip_address(authority)
                if (
                    ip.is_loopback
                    or ip.is_private
                    or ip.is_link_local
                    or ip.is_unspecified
                    or ip.is_reserved
                    or ip.is_multicast
                ):
                    raise InvalidOriginalUrlError(
                        f"Private/Internal IP '{authority}' in original URL is not accessible from the public internet."
                    )
            except ValueError:
                pass
            raise InvalidOriginalUrlError(
                f"Malformed original URL with unbracketed IPv6: {clean_url}"
            )

        parsed = urlparse(clean_url)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise InvalidOriginalUrlError(f"Malformed original URL: {clean_url}")

        if (
            hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
            or hostname.endswith(".localhost")
        ):
            raise InvalidOriginalUrlError(
                f"Localhost/loopback URL '{clean_url}' cannot be accessed by Meta reviewers. A public URL is required."
            )

        ip = _try_parse_ip_or_variant(hostname)
        if ip:
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_unspecified
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise InvalidOriginalUrlError(
                    f"Private/Internal IP '{hostname}' in original URL is not accessible from the public internet."
                )

        return cls(url=clean_url)
