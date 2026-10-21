# File: backend/app/infrastructure/automation/adspower_composition.py
from app.infrastructure.automation.adspower_policy import AdsPowerPolicy
from app.infrastructure.automation.adspower_client import AdsPowerClient
from app.infrastructure.automation.adspower_identity import RuntimeIdentity
from app.infrastructure.automation.adspower_budget import BrowserResourceBudget
from app.infrastructure.automation.adspower_cdp import AdsPowerCdp
from app.infrastructure.automation.adspower_acquire import ProfileAcquireFlow
from app.infrastructure.automation.adspower_cleanup import ProfileCleanupFlow
from app.infrastructure.automation.adspower_correlation import ProfileCorrelation
from app.infrastructure.automation.adspower_recovery import BrowserRecovery


def build_service(uow_factory, settings, *, max_sessions=None, maintenance=False,
                  transport=None, driver_factory=None, schema_check=None, read_factory=None):
    from app.infrastructure.automation.adspower_session import AdsPowerSessionService

    if max_sessions is not None:
        settings = settings.model_copy(update={
            "max_profile_sessions": min(settings.max_profile_sessions, max_sessions)})
    policy = AdsPowerPolicy(settings)
    identity = RuntimeIdentity(settings.identity_path)
    client = AdsPowerClient(settings, transport)
    budget = BrowserResourceBudget(uow_factory, identity, policy, read_factory=read_factory)
    cdp = AdsPowerCdp(policy, driver_factory)
    acquire = ProfileAcquireFlow(client, uow_factory, identity, budget, cdp, policy)
    cleanup = ProfileCleanupFlow(client, uow_factory, identity, budget, cdp, policy)
    correlation = ProfileCorrelation(client, identity, policy)
    recovery = BrowserRecovery(client, uow_factory, identity, budget, correlation, cleanup)
    return AdsPowerSessionService(client, uow_factory, identity, budget, cdp, acquire,
        cleanup, recovery, policy, maintenance=maintenance, schema_check=schema_check)
