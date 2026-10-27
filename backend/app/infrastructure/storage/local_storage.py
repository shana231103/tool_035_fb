# File: backend/app/infrastructure/storage/local_storage.py
from pathlib import Path
from app.domain.exceptions.evidence_errors import EvidenceFileError
from app.domain.ports.storage_service import IStorageService
from app.infrastructure.storage.image_sanitizer import ProofImageSanitizer
from app.infrastructure.storage.proof_file_io import ProofFileIO


class LocalStorageService(IStorageService):
    def __init__(
        self, base_storage_dir: str, public_base_url: str = "", *,
        max_proof_bytes: int = 10485760, max_proof_pixels: int = 20000000,
        max_encoded_proof_bytes: int = 20971520, proof_worker_concurrency: int = 1,
    ):
        self._root = Path(base_storage_dir).resolve()
        self._public_base_url = public_base_url.rstrip("/")
        self._io = ProofFileIO(
            self._root, ProofImageSanitizer(max_proof_bytes, max_proof_pixels, max_encoded_proof_bytes),
            proof_worker_concurrency,
        )
        (self._root / "screenshots").mkdir(parents=True, exist_ok=True)

    def _reference(self, category: str, name: str) -> str:
        return f"{self._public_base_url}/{category}/{name}"

    async def save_proof_file(self, filename: str, content: bytes) -> str:
        name = await self._io.save(filename, content)
        return self._reference("uploads", name)

    async def delete_proof_file(self, reference: str) -> None:
        prefix = self._reference("uploads", "")
        if not reference.startswith(prefix):
            raise EvidenceFileError("STORAGE_FAILED")
        await self._io.delete(reference[len(prefix):])

    async def save_screenshot(self, filename: str, content: bytes) -> str:
        destination = self._confined_path("screenshots", filename)
        await self._io._run(
            lambda: destination.write_bytes(content),
            lambda: destination.unlink(missing_ok=True),
        )
        return self._reference("screenshots", filename)

    def _confined_path(self, category: str, name: str) -> Path:
        if not name or name in {".", ".."} or any(c in name for c in "/\\:?%#"):
            raise EvidenceFileError("STORAGE_FAILED")
        directory = self._io._directory(category)
        path = directory / name
        if path.is_symlink() or path.resolve() != path:
            raise EvidenceFileError("STORAGE_FAILED")
        if path.exists() and self._io._reparse(path):
            raise EvidenceFileError("STORAGE_FAILED")
        return path

    async def get_local_path(self, relative_path: str) -> str:
        path = relative_path
        if self._public_base_url and path.startswith(self._public_base_url + "/"):
            path = path[len(self._public_base_url):]
        path = path.removeprefix("/")
        for category in ("screenshots", "uploads"):
            if path.startswith(category + "/"):
                return str(self._confined_path(category, path[len(category) + 1:]))
        for category in ("screenshots", "uploads"):
            candidate = self._confined_path(category, path)
            if candidate.exists() or category == "uploads":
                return str(candidate)
        raise EvidenceFileError("STORAGE_FAILED")

    async def shutdown(self) -> None:
        await self._io.shutdown()
