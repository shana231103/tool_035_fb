# File: backend/app/presentation/api/v1/mailbox_connections.py
from dataclasses import asdict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from app.application.dtos.mailbox_dtos import (
    BeginMailboxLoginDTO, MailboxMappingDTO, MailboxConnectionDTO, DeviceLoginPromptDTO,
    MailboxConfigurationDTO, ConfigureMailboxClientDTO,
)
from app.infrastructure.mail.meta_report_template import META_REPORT_TEMPLATE_VERSION
from app.infrastructure.mail.microsoft_auth import MicrosoftAuth
from app.application.use_cases.manage_mailbox_connection import ManageMailboxConnectionUseCase
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import MailboxMapping
from app.presentation.api.mailbox_guard import trusted_local_operator
from app.presentation.api.deps import get_manage_mailbox_connection_use_case, get_microsoft_auth

router = APIRouter(prefix="/mailbox-connections", tags=["Microsoft mailbox"],
                   dependencies=[Depends(trusted_local_operator)])


def safe_error(error):
    return HTTPException(409, error.reason, headers={"Cache-Control": "no-store"})


@router.get("/configuration", response_model=MailboxConfigurationDTO)
async def configuration(auth: MicrosoftAuth = Depends(get_microsoft_auth)):
    return MailboxConfigurationDTO(
        login_configured=bool(auth.client_id.strip()), client_id=auth.client_id,
        template_version=META_REPORT_TEMPLATE_VERSION,
        template_label="Meta — Please verify your email address",
    )


@router.put("/configuration", response_model=MailboxConfigurationDTO)
async def configure_client(dto: ConfigureMailboxClientDTO,
                           auth: MicrosoftAuth = Depends(get_microsoft_auth)):
    try:
        auth.configure_client_id(str(dto.client_id))
    except MailboxError as error:
        raise safe_error(error) from None
    return await configuration(auth)


@router.post("/login", status_code=202, response_model=DeviceLoginPromptDTO)
async def begin_login(dto: BeginMailboxLoginDTO,
                      use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    try:
        return DeviceLoginPromptDTO(**asdict(await use_case.begin_login(dto.account_hint)))
    except MailboxError as error:
        raise safe_error(error) from None


@router.get("/logins/{login_id}", response_model=MailboxConnectionDTO)
async def login_status(login_id: UUID,
                       use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    try:
        return MailboxConnectionDTO.from_view(await use_case.login_status(str(login_id)))
    except (KeyError, MailboxError):
        raise HTTPException(404, "Login unavailable.", headers={"Cache-Control": "no-store"}) from None


@router.delete("/logins/{login_id}", status_code=204)
async def cancel_login(login_id: UUID,
                       use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    await use_case.cancel_login(str(login_id))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("", response_model=list[MailboxConnectionDTO])
async def list_connections(
    use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case),
):
    return [MailboxConnectionDTO.from_view(v) for v in await use_case.list_connections()]


@router.put("/{connection_id}/mapping", response_model=MailboxConnectionDTO)
async def set_mapping(connection_id: UUID, dto: MailboxMappingDTO,
                      use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    try:
        mapping = MailboxMapping(dto.meta_email, dto.primary_email or dto.meta_email,
                                 dto.confirmed_aliases, dto.folders, dto.template_version)
        return MailboxConnectionDTO.from_view(await use_case.set_mapping(str(connection_id), mapping))
    except MailboxError as error:
        if error.reason == "MAPPING_INVALID":
            raise HTTPException(422, "Invalid mailbox mapping.") from None
        raise safe_error(error) from None
    except ValueError:
        raise HTTPException(422, "Invalid mailbox mapping.") from None


@router.delete("/{connection_id}", status_code=204)
async def disconnect(connection_id: UUID,
                      use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    await use_case.disconnect(str(connection_id))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
