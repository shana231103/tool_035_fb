from dataclasses import dataclass
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse
from app.domain.exceptions.domain_exceptions import InvalidMetaUrlError
from app.domain.value_objects.enums import PlatformType


@dataclass(frozen=True)
class TargetUrl:
    url: str
    platform: PlatformType
    content_type: str

    @classmethod
    def from_raw_url(cls, raw_url: str) -> "TargetUrl":
        clean_url = (raw_url or "").strip()
        if not clean_url:
            raise InvalidMetaUrlError("Target URL cannot be empty.")

        # Basic scheme validation
        if not re.match(r"^https?://", clean_url, re.IGNORECASE):
            clean_url = "https://" + clean_url

        parsed = urlparse(clean_url)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise InvalidMetaUrlError(
                f"URL '{clean_url}' is not a valid Meta platform URL (Facebook, Instagram, Threads)."
            )

        clean_lower = clean_url.lower()

        fb_domains = {"facebook.com", "fb.watch", "fb.com"}
        ig_domains = {"instagram.com", "instagr.am"}
        threads_domains = {"threads.net", "threads.com"}

        def matches_domain_family(host: str, domains: set) -> bool:
            return any(host == d or host.endswith("." + d) for d in domains)

        if matches_domain_family(hostname, fb_domains):
            platform = PlatformType.FACEBOOK
            if "/photo" in clean_lower or "fbid=" in clean_lower or "/photos" in clean_lower:
                content_type = "photo"
            elif "/reel" in clean_lower or "/watch" in clean_lower or "fb.watch" in hostname or "/videos" in clean_lower:
                content_type = "video"
            else:
                content_type = "post"
        elif matches_domain_family(hostname, ig_domains):
            platform = PlatformType.INSTAGRAM
            if "/reel/" in clean_lower:
                content_type = "reel"
            elif "/p/" in clean_lower:
                content_type = "post"
            elif "/stories/" in clean_lower:
                content_type = "story"
            else:
                content_type = "media"
        elif matches_domain_family(hostname, threads_domains):
            platform = PlatformType.THREADS
            content_type = "post"
        else:
            raise InvalidMetaUrlError(
                f"URL '{clean_url}' is not a valid Meta platform URL (Facebook, Instagram, Threads)."
            )

        return cls(url=clean_url, platform=platform, content_type=content_type)

    def extract_account_identifier(self) -> Optional[str]:
        """Extract username, handle, or page ID from the target URL."""
        parsed = urlparse(self.url)
        path = parsed.path.strip("/")
        segments = [s for s in path.split("/") if s]

        # 1. Threads
        if self.platform == PlatformType.THREADS:
            match = re.search(r"@([a-zA-Z0-9._]+)", path)
            if match:
                return f"@{match.group(1)}"
            if segments and not segments[0].startswith("@"):
                return f"@{segments[0]}"
            return None

        # 2. Instagram
        if self.platform == PlatformType.INSTAGRAM:
            ig_system = {
                "reel", "reels", "p", "stories", "explore", "direct",
                "tv", "share", "accounts", "about", "legal", "developer",
            }
            if not segments:
                return None
            first = segments[0]
            if first == "stories" and len(segments) > 1:
                user = segments[1].lstrip("@")
                if user and user not in ig_system:
                    return f"@{user}"
            elif first not in ig_system:
                user = first.lstrip("@")
                if re.match(r"^[a-zA-Z0-9._]+$", user):
                    return f"@{user}"
            return None

        # 3. Facebook
        if self.platform == PlatformType.FACEBOOK:
            q = parse_qs(parsed.query)
            # Query param id check (profile.php, permalink.php, story.php, photo.php, or if no segments)
            is_query_endpoint = (
                any(ep in path for ep in ["profile.php", "permalink.php", "story.php", "photo.php"])
                or not segments
            )
            if is_query_endpoint:
                if "id" in q and q["id"]:
                    return f"id={q['id'][0]}"
                return None

            fb_system = {
                "photo", "photos", "photo.php", "permalink.php", "story.php",
                "watch", "reel", "reels", "share", "groups", "events",
                "gaming", "marketplace", "messages", "login", "checkpoint",
                "help", "pages", "profile.php", "home.php", "media", "live",
            }
            first = segments[0]
            if first not in fb_system:
                user = first.lstrip("@")
                if re.match(r"^[a-zA-Z0-9._]+$", user):
                    return f"@{user}"
            return None

        return None
