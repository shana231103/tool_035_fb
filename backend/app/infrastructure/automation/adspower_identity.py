# File: backend/app/infrastructure/automation/adspower_identity.py
import base64
import errno
import hashlib
import hmac
import json
import os
import platform
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4
from app.domain.exceptions.browser_errors import BrowserOwnershipError
from app.domain.value_objects.browser_status import RuntimeBinding


@dataclass(frozen=True)
class InstallationIdentity:
    installation_id: UUID
    host_binding_digest: str
    signing_key: bytes = field(repr=False)


class RuntimeIdentity:
    def __init__(self, identity_path: Path, host_binding_provider: Callable[[], str] | None = None) -> None:
        self.path = Path(identity_path).resolve()
        self._provider_binding_id = None
        self._host = host_binding_provider or (lambda: f"{platform.node()}:{uuid_getnode()}")
        self._file = None
        self.value = None

    def _digest(self):
        return hashlib.sha256(f"{self._host()}:{self.path.parent}".encode()).hexdigest()

    def initialize(self) -> None:
        """Publish a complete sidecar under the lock after the caller proves an empty DB."""
        if self._file is None:
            raise BrowserOwnershipError()
        payload = {"installation_id": str(uuid4()), "host_binding_digest": self._digest(),
                   "signing_key": base64.b64encode(secrets.token_bytes(32)).decode()}
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows rename refuses an existing destination; POSIX link does likewise.
            publish = os.rename if os.name == "nt" else os.link
            publish(temporary, self.path)
        except OSError:
            raise BrowserOwnershipError() from None
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    raise BrowserOwnershipError() from None

    def acquire_lock(self) -> None:
        if self._file is not None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stream = open(self.path.parent / "browser-runtime.lock", "a+b")
        except OSError:
            raise BrowserOwnershipError() from None
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            contention = error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
            raise BrowserOwnershipError("BROWSER_INSTANCE_ACTIVE" if contention
                                        else "BROWSER_AUTHORITY_MISMATCH") from None
        self._file = stream

    def acquire(self) -> InstallationIdentity:
        self.acquire_lock()
        try:
            if self.value is not None:
                self.assert_authority()
                return self.value
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or any(not isinstance(raw.get(key), str) for key in
                    ("installation_id", "host_binding_digest", "signing_key")):
                raise ValueError
            self.value = InstallationIdentity(UUID(raw["installation_id"]), raw["host_binding_digest"],
                base64.b64decode(raw["signing_key"], validate=True))
            if self.value.host_binding_digest != self._digest() or len(self.value.signing_key) != 32:
                raise ValueError
        except (ValueError, TypeError, OSError):
            self.release()
            raise BrowserOwnershipError() from None
        return self.value

    @property
    def provider_binding_id(self) -> UUID | None:
        return self._provider_binding_id

    def bind_provider(self, provider_binding_id: UUID) -> None:
        self.assert_authority()
        if not isinstance(provider_binding_id, UUID):
            raise BrowserOwnershipError()
        if self._provider_binding_id is not None and self._provider_binding_id != provider_binding_id:
            raise BrowserOwnershipError("PROVIDER_BINDING_MISMATCH")
        self._provider_binding_id = provider_binding_id

    def _assert_bound(self):
        self.assert_authority()
        if self.provider_binding_id is None:
            raise BrowserOwnershipError()

    @property
    def binding(self) -> RuntimeBinding:
        self._assert_bound()
        return RuntimeBinding(self.value.installation_id, self.provider_binding_id, self.value.host_binding_digest)

    def assert_authority(self) -> None:
        if self._file is None or self.value is None or self.value.host_binding_digest != self._digest():
            raise BrowserOwnershipError()

    def verify_binding(self, binding: RuntimeBinding) -> None:
        self.assert_authority()
        if binding != self.binding:
            raise BrowserOwnershipError("PROVIDER_BINDING_MISMATCH")

    def verify_record(self, record):
        self._assert_bound()
        if (record.installation_id != self.value.installation_id
                or record.provider_binding_id != self.provider_binding_id):
            raise BrowserOwnershipError(operation_id=record.operation_id)

    def sign_marker(self, operation_id, nonce):
        self._assert_bound()
        value = f"rpt:{self.value.installation_id}:{operation_id}:{nonce}"
        return f"{value}:{hmac.new(self.value.signing_key, value.encode(), hashlib.sha256).hexdigest()}"

    def verify_marker(self, marker, record):
        self.verify_record(record)
        return hmac.compare_digest(marker, self.sign_marker(record.operation_id, record.marker_nonce))

    def release(self) -> None:
        stream, self._file = self._file, None
        self.value = None
        if stream is not None:
            stream.close()  # Closing the handle also releases the OS lock.


def uuid_getnode():
    from uuid import getnode
    return getnode()
