# File: backend/browser_maintenance.py
"""Offline operator maintenance. Never accepts keys or deletes provider profiles."""
import argparse
import asyncio
from uuid import UUID


class MaintenanceParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid maintenance arguments. Use --help for the required fields.\n")


def parser():
    result = MaintenanceParser(description=__doc__)
    modes = result.add_mutually_exclusive_group(required=True)
    modes.add_argument("--initialize", action="store_true", help="Create identity only for an empty browser ledger.")
    modes.add_argument("--confirm-external", action="store_true", help="Record verified external cleanup offline.")
    result.add_argument("--operation-id", type=UUID)
    result.add_argument("--expected-version", type=int)
    result.add_argument("--audit-reference")
    result.add_argument("--provider-terminal", action="store_true")
    result.add_argument("--verified-local-audit", action="store_true")
    return result


async def run(args):
    from app.core.config import settings
    from app.application.browser_readiness import BrowserCleanupUseCase
    from app.application.unit_of_work import SystemPurpose
    from app.domain.exceptions.browser_errors import BrowserError
    from app.domain.value_objects.browser_status import ExternalCleanupConfirmation
    from app.infrastructure.persistence.database import db_manager
    from app.infrastructure.persistence.schema_health import check_browser_schema
    from app.infrastructure.persistence.sql_unit_of_work import SystemUnitOfWorkFactory
    from app.infrastructure.automation.adspower_settings import AdsPowerSettings
    from app.infrastructure.automation.adspower_session import build_service
    browser_settings = AdsPowerSettings(_env_file=settings.model_config.get("env_file"))
    browser_settings = browser_settings.model_copy(update={"initialize_identity": args.initialize})
    system_factory = SystemUnitOfWorkFactory(db_manager)
    service = build_service(
        lambda: system_factory.open(SystemPurpose.PROVIDER_LEDGER, write=True), browser_settings,
        maintenance=True, schema_check=lambda: check_browser_schema(db_manager),
        read_factory=lambda: system_factory.open(SystemPurpose.PROVIDER_LEDGER, write=False))
    db_manager.init(settings.database_url, echo=False)
    try:
        readiness = await service.bootstrap()
        if readiness.state.value == "BLOCKED":
            print(readiness.safe_reason or "BROWSER_LEDGER_UNCERTAIN")
            return 1
        if args.initialize:
            print("Browser installation identity initialized or verified. No provider request was made.")
        else:
            confirmation = ExternalCleanupConfirmation(args.operation_id, args.expected_version,
                args.audit_reference, args.provider_terminal, args.verified_local_audit)
            outcome = await BrowserCleanupUseCase(service).confirm_external(confirmation)
            print(f"Browser cleanup confirmation: {outcome.state.value}.")
        return 0
    except BrowserError as error:
        print(error.code)
        return 1
    except (ValueError, OSError):
        print("Browser maintenance could not be verified. No forced cleanup was recorded.")
        return 1
    finally:
        await service.shutdown()
        await db_manager.close()


def main(argv=None):
    arg_parser = parser()
    args = arg_parser.parse_args(argv)
    if args.confirm_external and (args.operation_id is None or args.expected_version is None
            or args.expected_version < 0 or not args.audit_reference
            or not args.provider_terminal or not args.verified_local_audit):
        arg_parser.error("Required audit fields are missing.")
    try:
        return asyncio.run(run(args))
    except Exception:
        print("Browser maintenance configuration is unavailable. Contact technical support.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
