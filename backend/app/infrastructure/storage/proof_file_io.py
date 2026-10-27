# File: backend/app/infrastructure/storage/proof_file_io.py
import asyncio
import os
import logging
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from app.domain.exceptions.evidence_errors import EvidenceFileError
from app.infrastructure.storage.image_sanitizer import ProofImageSanitizer

logger = logging.getLogger(__name__)


async def drain_owned(task):
    """Keep ownership until completion despite repeated caller cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


class ProofFileIO:
    def __init__(self, root: Path, sanitizer: ProofImageSanitizer, concurrency: int = 1):
        if concurrency != 1:
            raise ValueError("Proof decoding requires one shared worker slot.")
        self.root = root.resolve()
        self.sanitizer = sanitizer
        self._slot = asyncio.Semaphore(1)
        self._closing = False
        self._operations = set()
        self._workers = set()
        for name in ("uploads", ".staging"):
            directory = self.root / name
            directory.mkdir(parents=True, exist_ok=True)
            self._directory(name)

    def _directory(self, name: str) -> Path:
        path = self.root / name
        try:
            if path.is_symlink() or path.resolve() != path or self._reparse(path):
                raise EvidenceFileError("STORAGE_FAILED")
        except OSError:
            raise EvidenceFileError("STORAGE_FAILED") from None
        return path

    @staticmethod
    def _reparse(path: Path) -> bool:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)

    def _proof_path(self, reference: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.png", reference):
            raise EvidenceFileError("STORAGE_FAILED")
        path = self._directory("uploads") / reference
        if path.exists() or path.is_symlink():
            if path.is_symlink() or self._reparse(path) or path.resolve() != path:
                raise EvidenceFileError("STORAGE_FAILED")
        return path

    async def _cleanup(self, abandoned):
        if abandoned is None:
            return
        cleanup = asyncio.create_task(asyncio.to_thread(abandoned))
        self._workers.add(cleanup)
        cancelled = None
        try:
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as error:
                cancelled = error
                await drain_owned(cleanup)
        except Exception:
            logger.warning("Proof cleanup unresolved: reason=CLEANUP_FAILED")
        finally:
            self._workers.discard(cleanup)
        return cancelled

    async def _run(self, operation, abandoned=None):
        if self._closing:
            raise EvidenceFileError("STORAGE_FAILED")
        completion = asyncio.get_running_loop().create_future()
        self._operations.add(completion)
        try:
            async with self._slot:
                if self._closing:
                    raise EvidenceFileError("STORAGE_FAILED")
                worker = asyncio.create_task(asyncio.to_thread(operation))
                self._workers.add(worker)
                try:
                    try:
                        return await asyncio.shield(worker)
                    except asyncio.CancelledError as cancelled:
                        try:
                            await drain_owned(worker)
                        except Exception:
                            logger.warning("Cancelled proof worker failed: reason=STORAGE_FAILED")
                        await self._cleanup(abandoned)
                        raise cancelled
                    except Exception:
                        cancelled = await self._cleanup(abandoned)
                        if cancelled:
                            raise cancelled
                        raise
                finally:
                    self._workers.discard(worker)
        except EvidenceFileError:
            raise
        except OSError:
            raise EvidenceFileError("STORAGE_FAILED") from None
        finally:
            completion.set_result(None)
            self._operations.discard(completion)

    async def save(self, filename: str, content: bytes) -> str:
        if not filename or "/" in filename or "\\" in filename or Path(filename).suffix.lower() not in {
            ".png", ".jpg", ".jpeg", ".webp",
        }:
            raise EvidenceFileError("UNSUPPORTED_IMAGE")
        reference = uuid4().hex + ".png"
        return await self._run(
            lambda: self._write(reference, content),
            lambda: self._proof_path(reference).unlink(missing_ok=True),
        )

    def _write(self, reference: str, content: bytes) -> str:
        normalized = self.sanitizer.normalize(content)
        destination = self._proof_path(reference)
        temporary = None
        try:
            descriptor, name = tempfile.mkstemp(prefix="proof-", suffix=".tmp", dir=self._directory(".staging"))
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(normalized.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            return reference
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    async def delete(self, reference: str) -> None:
        path = self._proof_path(reference)
        await self._run(lambda: path.unlink(missing_ok=True))

    async def shutdown(self) -> None:
        self._closing = True
        if self._operations:
            owned = asyncio.ensure_future(asyncio.gather(*tuple(self._operations)))
            try:
                await asyncio.shield(owned)
            except asyncio.CancelledError:
                await drain_owned(owned)
                raise
