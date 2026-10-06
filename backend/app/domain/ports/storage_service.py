# File: backend/app/domain/ports/storage_service.py
from abc import ABC, abstractmethod


class IStorageService(ABC):
    @abstractmethod
    async def save_proof_file(self, filename: str, content: bytes) -> str:
        """Archive a normalized raster; return an opaque generated reference."""
        raise NotImplementedError

    @abstractmethod
    async def delete_proof_file(self, reference: str) -> None:
        """Idempotently remove only a generated proof reference from this adapter."""
        raise NotImplementedError

    @abstractmethod
    async def get_local_path(self, relative_path: str) -> str:
        """Resolves absolute filesystem path for a stored upload or screenshot."""
        raise NotImplementedError
