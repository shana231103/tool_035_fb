# File: backend/app/infrastructure/persistence/repositories/postgres_proxy_repo.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.proxy_item import ProxyItem
from app.domain.ports.repositories import IProxyRepository
from app.domain.value_objects.enums import ProxyCountry, ProxyStatus
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import ProxyModel


class PostgresProxyRepository(IProxyRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, proxy_id: UUID) -> Optional[ProxyItem]:
        model = await self._session.get(ProxyModel, str(proxy_id))
        return DataMapper.proxy_to_domain(model) if model else None

    async def get_active_proxy(self, country: Optional[ProxyCountry] = None) -> Optional[ProxyItem]:
        query = select(ProxyModel).where(
            ProxyModel.status.in_([ProxyStatus.ACTIVE.value, ProxyStatus.TESTING.value])
        )
        if country:
            query = query.where(ProxyModel.country == country.value)

        query = query.order_by(ProxyModel.latency_ms.asc()).limit(1)
        result = await self._session.execute(query)
        model = result.scalar_one_or_none()
        return DataMapper.proxy_to_domain(model) if model else None

    async def list_all(self) -> List[ProxyItem]:
        stmt = select(ProxyModel).order_by(ProxyModel.country, ProxyModel.created_at)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.proxy_to_domain(m) for m in models]

    async def save(self, proxy: ProxyItem) -> None:
        model = await self._session.get(ProxyModel, str(proxy.id))
        if not model:
            self._session.add(DataMapper.proxy_to_model(proxy))
        else:
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

    async def delete(self, proxy_id: UUID) -> None:
        stmt = delete(ProxyModel).where(ProxyModel.id == str(proxy_id))
        await self._session.execute(stmt)
