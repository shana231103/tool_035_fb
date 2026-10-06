# File: backend/app/domain/entities/owner_profile.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
from app.domain.value_objects.email_address import EmailAddress
from app.domain.value_objects.enums import OwnerRole


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class OwnerProfile:
    id: UUID
    full_name: str
    email: EmailAddress
    country: str
    organization_name: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    rights_owner_name: str | None = None
    sender_name: str | None = None
    rights_jurisdiction: str | None = None
    owner_role: OwnerRole | None = None

    @classmethod
    def create(
        cls,
        full_name: str,
        email: str,
        country: str,
        organization_name: str = "",
        profile_id: UUID = None,
        rights_owner_name: str | None = None,
        sender_name: str | None = None,
        rights_jurisdiction: str | None = None,
        owner_role: OwnerRole | None = None,
    ) -> "OwnerProfile":
        clean_name = (full_name or "").strip()
        if not clean_name:
            raise ValueError("Owner full name is required.")

        email_vo = EmailAddress.from_string(email)
        clean_country = (country or "").strip().upper()
        if not clean_country:
            raise ValueError("Country is required.")

        return cls(
            id=profile_id or uuid4(),
            full_name=clean_name,
            email=email_vo,
            country=clean_country,
            organization_name=(organization_name or "").strip(),
            created_at=_utc_now(),
            rights_owner_name=(rights_owner_name or "").strip() or None,
            sender_name=(sender_name or "").strip() or None,
            rights_jurisdiction=(rights_jurisdiction or "").strip() or None,
            owner_role=OwnerRole(owner_role) if owner_role else None,
        )

    def validate_for_submission(self) -> None:
        if self.needs_completion:
            raise ValueError("Complete rights owner, sender, jurisdiction and owner role in profile.")
        if self.owner_role != OwnerRole.OWNER:
            raise ValueError("Only confirmed rights owners may submit. Update this profile explicitly to OWNER.")

    @property
    def submission_eligible(self) -> bool:
        return self.submission_block_reason is None

    @property
    def submission_block_reason(self) -> str | None:
        if self.needs_completion:
            return "Complete rights owner, sender, jurisdiction and owner role in profile."
        if self.owner_role != OwnerRole.OWNER:
            return "Only confirmed rights owners may submit. Update this profile explicitly to OWNER."
        return None

    @property
    def needs_completion(self) -> bool:
        return not self.owner_role or not all(
            value and value.strip()
            for value in (self.rights_owner_name, self.sender_name, self.rights_jurisdiction)
        )
