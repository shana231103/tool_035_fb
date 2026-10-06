# File: backend/app/domain/value_objects/email_address.py
from dataclasses import dataclass
import re
from app.domain.exceptions.domain_exceptions import InvalidEmailError


@dataclass(frozen=True)
class EmailAddress:
    value: str

    @classmethod
    def from_string(cls, raw_email: str) -> "EmailAddress":
        clean_email = (raw_email or "").strip().lower()
        if not clean_email:
            raise InvalidEmailError("Email address cannot be empty.")

        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, clean_email):
            raise InvalidEmailError(f"Email '{clean_email}' is not a valid email address.")

        return cls(value=clean_email)
