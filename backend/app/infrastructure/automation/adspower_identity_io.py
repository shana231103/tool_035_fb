# File: backend/app/infrastructure/automation/adspower_identity_io.py
import errno
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO


class ParentLockUnavailable(OSError):
    """The nonblocking operating-system lock has another owner."""


def acquire_parent_lock(parent: Path) -> BinaryIO:
    parent.mkdir(parents=True, exist_ok=True)
    handle = open(parent / "browser-runtime.lock", "a+b")
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise ParentLockUnavailable() from error
            raise
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        return handle
    except BaseException:
        handle.close()
        raise


def release_parent_lock(handle: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def publish_identity(path: Path, payload: bytes) -> None:
    """Publish a complete sidecar without replacing an existing name."""
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 8192:
        raise ValueError("Invalid identity payload")
    staging = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".browser-identity-",
                                         suffix=".tmp", dir=path.parent, delete=False) as stream:
            staging = Path(stream.name)
            if stream.write(payload) != len(payload):
                raise OSError("Incomplete identity write")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, path)
    finally:
        if staging is not None:
            with suppress(OSError):
                staging.unlink()
