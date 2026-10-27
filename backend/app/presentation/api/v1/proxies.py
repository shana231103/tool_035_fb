# File: backend/app/presentation/api/v1/proxies.py
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.application.dtos.proxy_dtos import (
    CreateProxyRequestDTO,
    ProxyResponseDTO,
    TestProxyResponseDTO,
)
from app.application.use_cases.manage_proxies import ManageProxiesUseCase
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.presentation.api.deps import get_manage_proxies_use_case

router = APIRouter(prefix="/proxies", tags=["Proxies"])


@router.post("", response_model=ProxyResponseDTO, status_code=status.HTTP_201_CREATED)
async def add_proxy(
    dto: CreateProxyRequestDTO,
    use_case: ManageProxiesUseCase = Depends(get_manage_proxies_use_case),
):
    try:
        return await use_case.add_proxy(dto)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("", response_model=List[ProxyResponseDTO])
async def list_proxies(
    use_case: ManageProxiesUseCase = Depends(get_manage_proxies_use_case),
):
    return await use_case.list_proxies()


@router.post("/{proxy_id}/test", response_model=TestProxyResponseDTO)
async def test_proxy(
    proxy_id: UUID,
    use_case: ManageProxiesUseCase = Depends(get_manage_proxies_use_case),
):
    try:
        return await use_case.test_proxy(proxy_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Proxy not found.")


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(
    proxy_id: UUID,
    use_case: ManageProxiesUseCase = Depends(get_manage_proxies_use_case),
):
    await use_case.delete_proxy(proxy_id)
