# File: backend/app/infrastructure/automation/adspower_correlation.py
from dataclasses import dataclass
from datetime import datetime, timezone
from app.infrastructure.automation.adspower_wire import ProfileQuery


@dataclass(frozen=True)
class CorrelationVerdict:
    profile_id: str | None = None
    proved: bool = False


class ProfileCorrelation:
    def __init__(self, client, identity, policy):
        self.client, self.identity, self.policy = client, identity, policy

    async def find_candidate(self, record):
        settings = self.policy.settings
        if not settings.correlation_enabled or not settings.correlation_capability_verified:
            return CorrelationVerdict()
        self.identity.verify_record(record)
        candidates = []
        for number in range(1, 11):
            page = await self.client.list_profiles(ProfileQuery(settings.group_id, page=number))
            for row in page.items:
                if row.group_id != settings.group_id or not self.identity.verify_marker(row.marker, record):
                    continue
                try:
                    created = datetime.fromtimestamp(float(row.created_at), timezone.utc)
                except (ValueError, OverflowError):
                    try:
                        created = datetime.fromisoformat(row.created_at)
                    except ValueError:
                        return CorrelationVerdict()
                if (created.tzinfo is None or created < record.created_at.replace(microsecond=0)
                        or created > record.updated_at.replace(microsecond=0) + self._window()):
                    return CorrelationVerdict()
                candidates.append(row.profile_id)
            if len(page.items) < 100:
                return CorrelationVerdict(candidates[0], True) if len(candidates) == 1 else CorrelationVerdict()
        return CorrelationVerdict()

    def _window(self):
        from datetime import timedelta
        return timedelta(seconds=self.policy.settings.create_timeout)
