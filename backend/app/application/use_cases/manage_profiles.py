# File: backend/app/application/use_cases/manage_profiles.py
from typing import List
from uuid import UUID
from app.application.dtos.profile_dtos import (
    CreateProfileRequestDTO,
    ProfileResponseDTO,
)
from app.application.unit_of_work import IUnitOfWork
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.exceptions.domain_exceptions import EntityNotFoundError


class ManageProfilesUseCase:
    def __init__(self, uow: IUnitOfWork):
        self._uow = uow

    async def create_profile(self, command: CreateProfileRequestDTO) -> ProfileResponseDTO:
        profile = OwnerProfile.create(
            full_name=command.full_name,
            email=command.email,
            country=command.country,
            organization_name=command.organization_name,
            rights_owner_name=command.rights_owner_name,
            sender_name=command.sender_name,
            rights_jurisdiction=command.rights_jurisdiction,
            owner_role=command.owner_role,
        )
        profile.validate_for_submission()
        async with self._uow:
            await self._uow.profiles.save(profile)

        return self._to_dto(profile)

    async def update_profile(self, profile_id: UUID, command: CreateProfileRequestDTO) -> ProfileResponseDTO:
        async with self._uow:
            existing = await self._uow.profiles.get_by_id(profile_id)
            if not existing:
                raise EntityNotFoundError("Profile not found.")
            profile = OwnerProfile.create(**command.model_dump(), profile_id=profile_id)
            profile.validate_for_submission()
            profile.created_at = existing.created_at
            await self._uow.profiles.save(profile)
        return self._to_dto(profile)

    async def list_profiles(self) -> List[ProfileResponseDTO]:
        async with self._uow:
            profiles = await self._uow.profiles.list_all()
        return [self._to_dto(p) for p in profiles]

    async def get_profile(self, profile_id: UUID) -> ProfileResponseDTO:
        async with self._uow:
            profile = await self._uow.profiles.get_by_id(profile_id)
            if not profile:
                raise EntityNotFoundError(f"Profile {profile_id} not found.")
        return self._to_dto(profile)

    async def delete_profile(self, profile_id: UUID) -> None:
        async with self._uow:
            await self._uow.profiles.delete(profile_id)

    @staticmethod
    def _to_dto(p: OwnerProfile) -> ProfileResponseDTO:
        return ProfileResponseDTO(
            id=p.id,
            full_name=p.full_name,
            email=p.email.value,
            country=p.country,
            organization_name=p.organization_name,
            created_at=p.created_at,
            rights_owner_name=p.rights_owner_name,
            sender_name=p.sender_name,
            rights_jurisdiction=p.rights_jurisdiction,
            owner_role=p.owner_role,
            needs_completion=p.needs_completion,
            submission_eligible=p.submission_eligible,
            submission_block_reason=p.submission_block_reason,
        )
