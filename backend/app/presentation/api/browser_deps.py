# File: backend/app/presentation/api/browser_deps.py
from app.application.browser_readiness import BrowserReadinessUseCase, BrowserCleanupUseCase
from app.domain.ports.browser_sessions import IBrowserControl

_control: IBrowserControl | None = None
_uow_factory = None


def configure_browser_control(uow_factory, max_contexts, schema_check, *, read_factory=None):
    from app.core.config import settings
    from app.infrastructure.automation.adspower_settings import AdsPowerSettings
    from app.infrastructure.automation.adspower_session import build_service
    global _control, _uow_factory
    browser_settings = AdsPowerSettings(_env_file=settings.model_config.get("env_file"))
    _control = build_service(uow_factory, browser_settings,
        max_sessions=max_contexts, schema_check=schema_check, read_factory=read_factory)
    _uow_factory = read_factory if read_factory is not None else uow_factory
    return _control


def get_browser_control() -> IBrowserControl:
    if _control is None:
        raise RuntimeError("Browser composition is unavailable.")
    return _control


def get_browser_readiness_use_case() -> BrowserReadinessUseCase:
    control = get_browser_control()
    return BrowserReadinessUseCase(control, _uow_factory)


def get_browser_cleanup_use_case() -> BrowserCleanupUseCase:
    return BrowserCleanupUseCase(get_browser_control())
