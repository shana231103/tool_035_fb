# File: backend/app/presentation/api/v1/profiles.py
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.application.dtos.profile_dtos import (
    CreateProfileRequestDTO,
    ProfileResponseDTO,
)
from app.application.use_cases.manage_profiles import ManageProfilesUseCase
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.presentation.api.deps import get_manage_profiles_use_case

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.post("", response_model=ProfileResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_profile(
    dto: CreateProfileRequestDTO,
    use_case: ManageProfilesUseCase = Depends(get_manage_profiles_use_case),
):
    try:
        return await use_case.create_profile(dto)
    except ValueError:
        raise HTTPException(status_code=400, detail="Provide a complete, confirmed OWNER profile.") from None


@router.put("/{profile_id}", response_model=ProfileResponseDTO)
async def update_profile(profile_id: UUID, dto: CreateProfileRequestDTO,
    use_case: ManageProfilesUseCase = Depends(get_manage_profiles_use_case)):
    try:
        return await use_case.update_profile(profile_id, dto)
    except EntityNotFoundError:
        raise HTTPException(404, "Profile not found.")
    except ValueError:
        raise HTTPException(400, "Provide a complete, confirmed OWNER profile.") from None


@router.get("", response_model=List[ProfileResponseDTO])
async def list_profiles(
    use_case: ManageProfilesUseCase = Depends(get_manage_profiles_use_case),
):
    return await use_case.list_profiles()


@router.get("/{profile_id}", response_model=ProfileResponseDTO)
async def get_profile(
    profile_id: UUID,
    use_case: ManageProfilesUseCase = Depends(get_manage_profiles_use_case),
):
    try:
        return await use_case.get_profile(profile_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found.")


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: UUID,
    use_case: ManageProfilesUseCase = Depends(get_manage_profiles_use_case),
):
    await use_case.delete_profile(profile_id)
