# File: backend/app/infrastructure/persistence/repositories/postgres_profile_repo.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.ports.repositories import IOwnerProfileRepository
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import OwnerProfileModel


class PostgresProfileRepository(IOwnerProfileRepository):
    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None):
        self._session = session
        self._operator_id = operator_id

    @property
    def operator_id(self) -> Optional[UUID]:
        return self._operator_id

    async def get_by_id(self, profile_id: UUID) -> Optional[OwnerProfile]:
        stmt = select(OwnerProfileModel).where(OwnerProfileModel.id == str(profile_id))
        if self._operator_id:
            stmt = stmt.where(
                OwnerProfileModel.operator_account_id == str(self._operator_id)
            )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return DataMapper.profile_to_domain(model) if model else None

    async def list_all(self) -> List[OwnerProfile]:
        stmt = select(OwnerProfileModel).order_by(OwnerProfileModel.created_at.desc())
        if self._operator_id:
            stmt = stmt.where(
                OwnerProfileModel.operator_account_id == str(self._operator_id)
            )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.profile_to_domain(m) for m in models]

    async def save(self, profile: OwnerProfile) -> None:
        if self._operator_id:
            profile.operator_id = self._operator_id

        model = await self._session.get(OwnerProfileModel, str(profile.id))
        if not model:
            model = DataMapper.profile_to_model(profile)
            if self._operator_id:
                model.operator_account_id = str(self._operator_id)
            self._session.add(model)
        else:
            if self._operator_id and model.operator_account_id != str(self._operator_id):
                return
            model.full_name = profile.full_name
            model.email = profile.email.value
            model.country = profile.country
            model.rights_owner_name = profile.rights_owner_name
            model.sender_name = profile.sender_name
            model.rights_jurisdiction = profile.rights_jurisdiction
            model.owner_role = profile.owner_role.value if profile.owner_role else None
            model.organization_name = profile.organization_name

    async def delete(self, profile_id: UUID) -> None:
        stmt = delete(OwnerProfileModel).where(OwnerProfileModel.id == str(profile_id))
        if self._operator_id:
            stmt = stmt.where(
                OwnerProfileModel.operator_account_id == str(self._operator_id)
            )
        await self._session.execute(stmt)
