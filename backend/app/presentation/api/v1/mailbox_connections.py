# File: backend/app/presentation/api/v1/mailbox_connections.py
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from app.application.dtos.mailbox_dtos import (
    ReserveMailboxDTO, ConnectMailboxDTO, MailboxMappingDTO, MailboxConnectionDTO,
    MailboxCapabilitiesDTO, MailboxReservationDTO,
)
from app.application.use_cases.manage_mailbox_connection import ManageMailboxConnectionUseCase
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_credentials import parse_mailbox_credentials
from app.domain.value_objects.mailbox_verification import MailboxMapping
from app.infrastructure.mail.meta_report_template import META_REPORT_TEMPLATE_VERSION
from app.presentation.api.mailbox_guard import trusted_local_operator
from app.presentation.api.deps import get_manage_mailbox_connection_use_case

router = APIRouter(prefix="/mailbox-connections", tags=["Microsoft mailbox"],
                   dependencies=[Depends(trusted_local_operator)])


def safe_error(error):
    return HTTPException(409, error.reason, headers={"Cache-Control": "no-store"})


@router.get("/capabilities", response_model=MailboxCapabilitiesDTO)
async def capabilities():
    return MailboxCapabilitiesDTO(credential_format="Mail|Refresh_Token|Client_id",
        template_version=META_REPORT_TEMPLATE_VERSION,
        template_label="Meta — Please verify your email address")


@router.post("/reservations", status_code=201, response_model=MailboxReservationDTO)
async def reserve_connection(dto: ReserveMailboxDTO,
    use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    try:
        return MailboxReservationDTO(**asdict(await use_case.reserve_connection()))
    except MailboxError as error:
        raise safe_error(error) from None


@router.post("/connect", response_model=MailboxConnectionDTO)
async def connect(dto: ConnectMailboxDTO,
    use_case: ManageMailboxConnectionUseCase = Depends(get_manage_mailbox_connection_use_case)):
    try:
        credentials = parse_mailbox_credentials(dto.credentials.get_secret_value())
        return MailboxConnectionDTO.from_view(await use_case.connect(str(dto.connection_id), credentials))
    except MailboxError as error:
        if error.reason == "INVALID_CREDENTIAL_FORMAT":
            raise HTTPException(422, "Invalid request.", headers={"Cache-Control": "no-store"}) from None
        raise safe_error(error) from None


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
