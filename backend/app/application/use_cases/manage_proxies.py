# File: backend/app/application/use_cases/manage_proxies.py
from typing import List, Optional
from uuid import UUID
from app.application.dtos.proxy_dtos import (
    CreateProxyRequestDTO,
    ProxyResponseDTO,
    TestProxyResponseDTO,
)
from app.application.unit_of_work import IUnitOfWork
from app.domain.entities.proxy_item import ProxyItem
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.ports.proxy_health import IProxyHealthService


class ManageProxiesUseCase:
    def __init__(self, uow: IUnitOfWork, health_service: IProxyHealthService):
        self._uow = uow
        self._health_service = health_service

    async def add_proxy(self, command: CreateProxyRequestDTO) -> ProxyResponseDTO:
        proxy = ProxyItem.create(
            host=command.host,
            port=command.port,
            country=command.country,
            protocol=command.protocol,
            username=command.username,
            password=command.password,
        )
        async with self._uow:
            await self._uow.proxies.save(proxy)

        return self._to_dto(proxy)

    async def list_proxies(self) -> List[ProxyResponseDTO]:
        async with self._uow:
            proxies = await self._uow.proxies.list_all()
        return [self._to_dto(p) for p in proxies]

    async def test_proxy(self, proxy_id: UUID) -> TestProxyResponseDTO:
        async with self._uow:
            proxy = await self._uow.proxies.get_by_id(proxy_id)
            if not proxy:
                raise EntityNotFoundError(f"Proxy {proxy_id} not found.")

        result = await self._health_service.check_proxy(
            server_url=proxy.get_server_url(),
            username=proxy.username,
            password=proxy.password,
        )

        async with self._uow:
            if result.is_alive:
                proxy.mark_active(result.latency_ms)
            else:
                proxy.mark_failed()
            await self._uow.proxies.save(proxy)

        return TestProxyResponseDTO(
            proxy_id=proxy.id,
            is_alive=result.is_alive,
            latency_ms=result.latency_ms,
            status=proxy.status,
            error=result.error or None,
        )

    async def delete_proxy(self, proxy_id: UUID) -> None:
        async with self._uow:
            await self._uow.proxies.delete(proxy_id)

    @staticmethod
    def _to_dto(p: ProxyItem) -> ProxyResponseDTO:
        return ProxyResponseDTO(
            id=p.id,
            protocol=p.protocol,
            host=p.host,
            port=p.port,
            country=p.country,
            username=p.username,
            status=p.status,
            latency_ms=p.latency_ms,
            consecutive_failures=p.consecutive_failures,
            created_at=p.created_at,
            last_checked_at=p.last_checked_at,
        )
