# File: backend/app/infrastructure/auth/session_secrets.py
"""Cryptographic utilities for session cookies, token digests, and derived CSRF tokens."""

import base64
import hashlib
import hmac
import re
import secrets
from app.domain.ports.operator_security import ISessionSecrets

CSRF_CONTEXT = b"operator-csrf-v1"
BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class SessionSecrets(ISessionSecrets):
    """Generates and verifies cryptographic session tokens and derived CSRF digests."""

    def new_secret(self) -> str:
        token_bytes = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")

    def _validate_secret(self, secret: str) -> bytes:
        if not secret or not isinstance(secret, str):
            raise ValueError("Session secret must be a non-empty string.")
        if not secret.isascii():
            raise ValueError("Session secret must contain only ASCII characters.")
        if not BASE64URL_PATTERN.match(secret):
            raise ValueError("Session secret must be a canonical 43-character base64url string.")
        return secret.encode("ascii")

    def digest(self, secret: str) -> bytes:
        raw_bytes = self._validate_secret(secret)
        return hashlib.sha256(raw_bytes).digest()

    def csrf(self, secret: str) -> str:
        key = self._validate_secret(secret)
        sig = hmac.new(key, CSRF_CONTEXT, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def verify_csrf(self, secret: str, supplied: str) -> bool:
        if not secret or not supplied or not isinstance(supplied, str):
            return False
        try:
            expected = self.csrf(secret)
        except ValueError:
            return False
        return hmac.compare_digest(expected, supplied)
