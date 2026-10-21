# File: backend/app/presentation/api/deps.py
import os
from fastapi import Depends
from app.application.unit_of_work import IUnitOfWork, SystemPurpose
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_auth import get_current_principal
from app.presentation.api.operator_composition import get_scoped_uow_factory
from app.application.use_cases.manage_profiles import ManageProfilesUseCase
from app.application.use_cases.manage_proxies import ManageProxiesUseCase
from app.application.mailbox_sessions import MailboxAttemptSessions
from app.application.mailbox_correlation import MailboxCorrelationPolicy
from app.application.use_cases.collect_email_verification_code import CollectEmailVerificationCodeUseCase
from app.application.use_cases.submit_email_verification_code import SubmitEmailVerificationCodeUseCase
from app.application.use_cases.manage_mailbox_connection import ManageMailboxConnectionUseCase
from app.infrastructure.mail.microsoft_refresh_token_auth import MicrosoftRefreshTokenAuth
from app.infrastructure.mail.mailbox_registry import MailboxRegistry
from app.infrastructure.mail.microsoft_mailbox_connections import MicrosoftMailboxConnections
from app.infrastructure.mail.graph_transport import GraphTransport
from app.infrastructure.mail.microsoft_graph_reader import MicrosoftGraphCodeReader
from app.infrastructure.mail.meta_report_template import (
    META_REPORT_TEMPLATE_VERSION, create_meta_report_otp_parser,
)
from app.infrastructure.automation.otp_dom_contract import OtpDomContract
from app.core.config import settings
from app.domain.ports.automation_driver import IAutomationDriver
from app.domain.ports.notifier import IEventNotifier
from app.domain.ports.proxy_health import IProxyHealthService
from app.domain.ports.storage_service import IStorageService
from app.infrastructure.verification.in_memory_broker import InMemoryVerificationBroker
from app.presentation.api.browser_deps import configure_browser_control, get_browser_control
from app.infrastructure.automation.anticaptcha_client import AntiCaptchaClient
from app.infrastructure.automation.recaptcha_solver import RecaptchaSolver
from app.infrastructure.automation.playwright_reporter import PlaywrightMetaReporter
from app.infrastructure.network.http_proxy_checker import HttpProxyChecker
from app.infrastructure.notifier.websocket_notifier import WebSocketNotifier
from app.infrastructure.persistence.database import db_manager
from app.infrastructure.persistence.sql_unit_of_work import SqlAlchemyUnitOfWork, SystemUnitOfWorkFactory
from app.infrastructure.persistence.schema_health import check_browser_schema
from app.infrastructure.storage.local_storage import LocalStorageService
from app.presentation.ws.socket_manager import socket_manager

# Singleton instances
_browser_control = configure_browser_control(
    lambda: SystemUnitOfWorkFactory(db_manager).open(SystemPurpose.PROVIDER_LEDGER),
    settings.max_browser_contexts, lambda: check_browser_schema(db_manager),
    read_factory=lambda: SystemUnitOfWorkFactory(db_manager).open(
        SystemPurpose.PROVIDER_LEDGER, write=False))
_storage_service = LocalStorageService(
    base_storage_dir=settings.base_storage_dir,
    public_base_url=settings.public_base_url,
    max_proof_bytes=settings.max_proof_bytes, max_proof_pixels=settings.max_proof_pixels,
    max_encoded_proof_bytes=settings.max_encoded_proof_bytes,
    proof_worker_concurrency=settings.proof_worker_concurrency,
)
_proxy_health_service = HttpProxyChecker()
_notifier = WebSocketNotifier()
_verification = InMemoryVerificationBroker()
_mailbox_sessions = MailboxAttemptSessions()
_microsoft_auth = MicrosoftRefreshTokenAuth(
    authority=settings.microsoft_authority,
    http_timeout=settings.microsoft_http_timeout,
)
_mailbox_registry = MailboxRegistry(
    mapping_busy=_mailbox_sessions.is_connection_busy,
    evidence_versions=(META_REPORT_TEMPLATE_VERSION,),
)
_graph_transport = GraphTransport(_microsoft_auth, http_timeout=settings.microsoft_http_timeout)
_mailbox_connections = MicrosoftMailboxConnections(
    auth=_microsoft_auth,
    registry=_mailbox_registry,
    probe=_graph_transport,
    template_version=META_REPORT_TEMPLATE_VERSION,
)
_mailbox_sessions.connections = _mailbox_connections
_mailbox_reader = MicrosoftGraphCodeReader(_graph_transport, create_meta_report_otp_parser())
_email_collector = CollectEmailVerificationCodeUseCase(
    _mailbox_connections, _mailbox_reader, SubmitEmailVerificationCodeUseCase(_verification),
    _verification, _mailbox_sessions,
    MailboxCorrelationPolicy(fresh_versions=(META_REPORT_TEMPLATE_VERSION,)),
    poll_interval=settings.graph_poll_interval, max_requests=settings.graph_request_budget,
    max_pages=settings.graph_page_budget, max_bodies=settings.graph_body_budget,
)

# Hook up WebSocketNotifier to WebSocketManager
_notifier.register_broadcast_callback(socket_manager.publish_json)

_anticaptcha_client = (
    AntiCaptchaClient(settings.anticaptcha_api_key, timeout=settings.anticaptcha_timeout)
    if settings.anticaptcha_api_key
    else None
)
_recaptcha_solver = RecaptchaSolver(_anticaptcha_client, timeout_sec=settings.anticaptcha_timeout)

_playwright_reporter = PlaywrightMetaReporter(
    page_provider=_browser_control,
    screenshots_dir=os.path.join(settings.base_storage_dir, "screenshots"),
    verification=_verification, navigation_timeout_ms=settings.navigation_timeout_ms,
    otp_timeout=settings.email_verification_timeout, max_code_attempts=settings.max_code_attempts,
    max_resends=settings.max_code_resends, receipt_timeout_ms=settings.receipt_timeout_ms,
    collector=_email_collector,
    otp_contract=OtpDomContract.meta_report(),
    captcha_solver=_recaptcha_solver,
)


def get_unit_of_work(
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> IUnitOfWork:
    if principal is None:
        raise RuntimeError("An authenticated owner is required for a scoped UoW.")
    return SqlAlchemyUnitOfWork(db_manager, operator_id=principal.operator_id)


def get_storage_service() -> IStorageService:
    return _storage_service


def get_proxy_health_service() -> IProxyHealthService:
    return _proxy_health_service


def get_notifier() -> IEventNotifier:
    return _notifier


def get_automation_driver() -> IAutomationDriver:
    return _playwright_reporter


def get_verification_broker() -> InMemoryVerificationBroker:
    return _verification


def get_manage_proxies_use_case(
    principal: OperatorPrincipal = Depends(get_current_principal),
    health: IProxyHealthService = Depends(get_proxy_health_service),
) -> ManageProxiesUseCase:
    scoped = get_scoped_uow_factory()
    return ManageProxiesUseCase(scoped.operator(principal.operator_id, write=True), health)


def get_manage_profiles_use_case(
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> ManageProfilesUseCase:
    scoped = get_scoped_uow_factory()
    return ManageProfilesUseCase(scoped.operator(principal.operator_id, write=True))


def get_manage_mailbox_connection_use_case(
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> ManageMailboxConnectionUseCase:
    return ManageMailboxConnectionUseCase(
        _mailbox_connections, _mailbox_sessions,
        owner=principal.operator_id, session_id=principal.session_id,
    )


def get_mailbox_connections():
    return _mailbox_connections


def get_mailbox_sessions():
    return _mailbox_sessions


def get_graph_transport():
    return _graph_transport


def get_microsoft_auth():
    return _microsoft_auth


def get_queue_orchestrator():
    return None
