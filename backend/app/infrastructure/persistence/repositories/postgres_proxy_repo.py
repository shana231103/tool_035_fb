# File: backend/app/infrastructure/persistence/repositories/postgres_proxy_repo.py
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.proxy_item import ProxyItem
from app.domain.ports.repositories import IProxyRepository
from app.domain.value_objects.enums import ProxyCountry, ProxyStatus
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import ProxyModel
from app.infrastructure.persistence.ownership_models import ProxyOwnerRefModel


class PostgresProxyRepository(IProxyRepository):
    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None):
        self._session = session
        self._operator_id = operator_id

    @property
    def operator_id(self) -> Optional[UUID]:
        return self._operator_id

    async def get_by_id(self, proxy_id: UUID) -> Optional[ProxyItem]:
        stmt = select(ProxyModel).where(
            ProxyModel.id == str(proxy_id),
            ProxyModel.deleted_at.is_(None),
        )
        if self._operator_id:
            stmt = stmt.where(ProxyModel.operator_account_id == str(self._operator_id))
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return DataMapper.proxy_to_domain(model) if model else None

    async def get_active_proxy(
        self, country: Optional[ProxyCountry] = None
    ) -> Optional[ProxyItem]:
        query = select(ProxyModel).where(
            ProxyModel.status.in_([ProxyStatus.ACTIVE.value, ProxyStatus.TESTING.value]),
            ProxyModel.deleted_at.is_(None),
        )
        if self._operator_id:
            query = query.where(
                ProxyModel.operator_account_id == str(self._operator_id)
            )
        if country:
            query = query.where(ProxyModel.country == country.value)

        query = query.order_by(ProxyModel.latency_ms.asc()).limit(1)
        result = await self._session.execute(query)
        model = result.scalar_one_or_none()
        return DataMapper.proxy_to_domain(model) if model else None

    async def list_all(self) -> List[ProxyItem]:
        stmt = (
            select(ProxyModel)
            .where(ProxyModel.deleted_at.is_(None))
            .order_by(ProxyModel.country, ProxyModel.created_at)
        )
        if self._operator_id:
            stmt = stmt.where(ProxyModel.operator_account_id == str(self._operator_id))
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.proxy_to_domain(m) for m in models]

    async def save(self, proxy: ProxyItem) -> None:
        if self._operator_id:
            proxy.operator_id = self._operator_id

        model = await self._session.get(ProxyModel, str(proxy.id))
        if not model:
            model = DataMapper.proxy_to_model(proxy)
            if self._operator_id:
                model.operator_account_id = str(self._operator_id)
            self._session.add(model)
        else:
            if self._operator_id and model.operator_account_id != str(self._operator_id):
                return
            model.protocol = proxy.protocol
            model.host = proxy.host
            model.port = proxy.port
            model.country = proxy.country.value
            model.username = proxy.username
            model.password = proxy.password
            model.status = proxy.status.value
            model.latency_ms = proxy.latency_ms
            model.consecutive_failures = proxy.consecutive_failures
            model.last_checked_at = proxy.last_checked_at
            model.deleted_at = proxy.deleted_at

        # Maintain immutable owner reference
        if self._operator_id:
            ref = await self._session.get(
                ProxyOwnerRefModel, (str(proxy.id), str(self._operator_id))
            )
            if not ref:
                self._session.add(
                    ProxyOwnerRefModel(
                        proxy_id=str(proxy.id),
                        operator_account_id=str(self._operator_id),
                    )
                )

    async def delete(self, proxy_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(ProxyModel)
            .where(ProxyModel.id == str(proxy_id))
            .values(
                deleted_at=now,
                username=None,
                password=None,
                status=ProxyStatus.DEAD.value,
            )
        )
        if self._operator_id:
            stmt = stmt.where(ProxyModel.operator_account_id == str(self._operator_id))
        await self._session.execute(stmt)
