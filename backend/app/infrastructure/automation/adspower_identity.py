# File: backend/app/infrastructure/automation/adspower_identity.py
import base64
import hashlib
import hmac
import json
import platform
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4
from app.domain.exceptions.browser_errors import BrowserOwnershipError
from app.domain.value_objects.browser_status import RuntimeBinding
from app.infrastructure.automation.adspower_identity_io import (
    ParentLockUnavailable, acquire_parent_lock, publish_identity, release_parent_lock,
)


@dataclass(frozen=True)
class InstallationIdentity:
    installation_id: UUID
    host_binding_digest: str
    signing_key: bytes = field(repr=False)


class RuntimeIdentity:
    def __init__(self, identity_path: Path,
                 host_binding_provider: Callable[[], str] | None = None,
                 provider_binding_id: UUID | None = None) -> None:
        self.path = Path(identity_path).resolve()
        self._provider_hint = provider_binding_id
        self._provider_binding_id = None
        self._host = host_binding_provider or (lambda: f"{platform.node()}:{uuid_getnode()}")
        self._file = None
        self.value = None

    def _digest(self):
        return hashlib.sha256(f"{self._host()}:{self.path.parent}".encode()).hexdigest()

    def acquire_lock(self) -> None:
        if self._file is not None:
            self.assert_locked()
            return
        try:
            self._file = acquire_parent_lock(self.path.parent)
        except ParentLockUnavailable:
            raise BrowserOwnershipError("BROWSER_INSTANCE_ACTIVE") from None
        except OSError:
            raise BrowserOwnershipError() from None

    def assert_locked(self) -> None:
        if self._file is None or self._file.closed:
            raise BrowserOwnershipError()

    def load(self) -> InstallationIdentity:
        self.assert_locked()
        previous = self.value
        self.value = None
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(8193)
            if len(payload) > 8192:
                raise ValueError
            raw = json.loads(payload.decode("utf-8"))
            fields = ("installation_id", "host_binding_digest", "signing_key")
            if not isinstance(raw, dict) or any(type(raw.get(key)) is not str for key in fields):
                raise ValueError
            value = InstallationIdentity(UUID(raw["installation_id"]), raw["host_binding_digest"],
                base64.b64decode(raw["signing_key"], validate=True))
            if value.host_binding_digest != self._digest() or len(value.signing_key) != 32:
                raise ValueError
            if previous is not None and value != previous:
                raise ValueError
        except (ValueError, OSError, RecursionError):
            raise BrowserOwnershipError() from None
        self.value = value
        return value

    def initialize(self) -> InstallationIdentity:
        """Publish fresh installation authority only while owning the parent lock."""
        self.assert_locked()
        payload = {"installation_id": str(uuid4()), "host_binding_digest": self._digest(),
                   "signing_key": base64.b64encode(secrets.token_bytes(32)).decode()}
        try:
            publish_identity(self.path, json.dumps(payload).encode("utf-8"))
        except (ValueError, OSError):
            raise BrowserOwnershipError() from None
        return self.load()

    def acquire(self) -> InstallationIdentity:
        """Compatibility wrapper for callers with an existing sidecar."""
        self.acquire_lock()
        try:
            if self.value is None:
                self.load()
            self.assert_authority()
            if self._provider_hint is not None:
                self.bind_provider(self._provider_hint)
            return self.value
        except BaseException:
            self.release()
            raise

    def bind_provider(self, provider_id: UUID) -> None:
        self.assert_authority()
        if not isinstance(provider_id, UUID):
            raise BrowserOwnershipError()
        if self.provider_binding_id is not None and self.provider_binding_id != provider_id:
            raise BrowserOwnershipError("PROVIDER_BINDING_MISMATCH")
        self._provider_binding_id = provider_id

    @property
    def provider_binding_id(self) -> UUID | None:
        return self._provider_binding_id

    @property
    def binding(self) -> RuntimeBinding:
        self.assert_authority()
        if not isinstance(self.provider_binding_id, UUID):
            raise BrowserOwnershipError()
        return RuntimeBinding(self.value.installation_id, self.provider_binding_id,
                              self.value.host_binding_digest)

    def assert_authority(self) -> None:
        self.assert_locked()
        if self.value is None or self.value.host_binding_digest != self._digest():
            raise BrowserOwnershipError()

    def verify_installation(self, binding: RuntimeBinding) -> None:
        self.assert_authority()
        if (not isinstance(binding, RuntimeBinding) or binding.schema_version != 1
                or binding.installation_id != self.value.installation_id
                or binding.host_binding_digest != self.value.host_binding_digest):
            raise BrowserOwnershipError()

    def verify_binding(self, binding: RuntimeBinding | None) -> None:
        self.verify_installation(binding)
        if binding != self.binding:
            raise BrowserOwnershipError("PROVIDER_BINDING_MISMATCH")

    def verify_record(self, record):
        binding = self.binding
        if (record.installation_id != binding.installation_id
                or record.provider_binding_id != binding.provider_binding_id):
            raise BrowserOwnershipError(operation_id=record.operation_id)

    def sign_marker(self, operation_id, nonce):
        binding = self.binding
        value = f"rpt:{binding.installation_id}:{operation_id}:{nonce}"
        return f"{value}:{hmac.new(self.value.signing_key, value.encode(), hashlib.sha256).hexdigest()}"

    def verify_marker(self, marker, record):
        self.verify_record(record)
        return hmac.compare_digest(marker, self.sign_marker(record.operation_id, record.marker_nonce))

    def release(self) -> None:
        handle, self._file = self._file, None
        self.value = None
        self._provider_binding_id = None
        if handle is not None:
            try:
                release_parent_lock(handle)
            except OSError:
                raise BrowserOwnershipError() from None


def uuid_getnode():
    from uuid import getnode
    return getnode()
