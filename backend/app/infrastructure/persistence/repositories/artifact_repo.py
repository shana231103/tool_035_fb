# File: backend/app/infrastructure/persistence/repositories/artifact_repo.py
"""SQLAlchemy repository for operator artifacts and proof/screenshot ownership metadata."""

from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.repositories import IArtifactRepository
from app.domain.value_objects.operator_identity import ArtifactKind, ArtifactRecord
from app.infrastructure.persistence.ownership_models import OperatorArtifactModel


class SqlArtifactRepository(IArtifactRepository):
    """Manages metadata authorization records for storage files."""

    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None):
        self._session = session
        self._operator_id = operator_id

    @property
    def operator_id(self) -> Optional[UUID]:
        return self._operator_id

    def _to_record(self, m: OperatorArtifactModel) -> ArtifactRecord:
        return ArtifactRecord(
            id=UUID(m.id),
            operator_id=UUID(m.operator_account_id),
            job_id=UUID(m.job_id) if m.job_id else None,
            task_id=UUID(m.task_id) if m.task_id else None,
            kind=ArtifactKind(m.kind),
            storage_key=m.storage_key,
            created_at=m.created_at,
        )

    async def get_by_key(
        self, key: str, kind: ArtifactKind
    ) -> Optional[ArtifactRecord]:
        stmt = select(OperatorArtifactModel).where(
            OperatorArtifactModel.storage_key == key,
            OperatorArtifactModel.kind == kind.value,
        )
        if self._operator_id:
            stmt = stmt.where(
                OperatorArtifactModel.operator_account_id == str(self._operator_id)
            )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def add(self, record: ArtifactRecord) -> None:
        if self._operator_id is not None and record.operator_id != self._operator_id:
            raise ValueError("Artifact owner does not match scope.")
        if record.job_id is None and record.task_id is None:
            raise ValueError("Artifact requires an owned resource.")
        model = OperatorArtifactModel(
            id=str(record.id),
            operator_account_id=str(self._operator_id or record.operator_id),
            job_id=str(record.job_id) if record.job_id else None,
            task_id=str(record.task_id) if record.task_id else None,
            kind=record.kind.value,
            storage_key=record.storage_key,
            created_at=record.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        if record.task_id is not None:
            from app.infrastructure.persistence.task_models import TaskArtifactLinkModel
            self._session.add(TaskArtifactLinkModel(artifact_id=str(record.id), task_id=str(record.task_id), operator_account_id=str(record.operator_id), kind=record.kind.value, created_at=record.created_at))
            await self._session.flush()

    async def list_for_task(self, task_id: UUID) -> List[ArtifactRecord]:
        stmt = select(OperatorArtifactModel).where(
            OperatorArtifactModel.task_id == str(task_id)
        )
        if self._operator_id:
            stmt = stmt.where(
                OperatorArtifactModel.operator_account_id == str(self._operator_id)
            )
        res = await self._session.execute(stmt)
        models = res.scalars().all()
        return [self._to_record(m) for m in models]
