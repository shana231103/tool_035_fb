# File: backend/manage_accounts.py
"""CLI utility for operator account administration and legacy data assignment."""

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import sys
from uuid import UUID

from app.application.operator_accounts import OperatorAccountService
from app.core.config import settings
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.persistence.database import db_manager
from app.infrastructure.persistence.legacy_ownership import LegacyOwnershipService
from app.infrastructure.persistence.operator_uow import AuthUnitOfWorkFactory


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


async def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Operator Account Administration CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Create new operator account")
    create_p.add_argument("username", help="Unique username")

    reset_p = sub.add_parser("reset-password", help="Reset account password")
    reset_p.add_argument("username", help="Target username")

    dis_p = sub.add_parser("disable", help="Disable account")
    dis_p.add_argument("username", help="Target username")

    en_p = sub.add_parser("enable", help="Enable account")
    en_p.add_argument("username", help="Target username")

    rev_p = sub.add_parser("revoke-sessions", help="Revoke all sessions for account")
    rev_p.add_argument("username", help="Target username")

    sub.add_parser("list", help="List all operator accounts")

    prev_p = sub.add_parser("preview-legacy", help="Preview legacy quarantine migration")
    prev_p.add_argument("target_username", help="Destination username")

    apply_p = sub.add_parser("apply-legacy", help="Apply legacy quarantine migration")
    apply_p.add_argument("target_username", help="Destination username")
    apply_p.add_argument("digest", help="Expected manifest digest")

    args = parser.parse_args()

    db_manager.init(settings.database_url)
    factory = AuthUnitOfWorkFactory(db_manager._sessionmaker)
    hasher = Argon2PasswordHasher()
    clock = SystemClock()
    service = OperatorAccountService(factory, hasher, clock)

    try:
        if not settings.database_url.startswith("sqlite"):
            from app.infrastructure.persistence.schema_health import check_schema
            await check_schema(db_manager)
        if args.command == "create":
            pwd = getpass.getpass("Enter password (min 12 chars): ")
            pwd2 = getpass.getpass("Confirm password: ")
            if pwd != pwd2:
                sys.exit("Passwords do not match.")
            meta = await service.create(args.username, pwd)
            print(f"Created operator account: {meta.id} ({meta.username_display})")

        elif args.command == "reset-password":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.username.casefold())
            if not acc:
                sys.exit(f"User {args.username} not found")
            pwd = getpass.getpass("Enter new password: ")
            pwd2 = getpass.getpass("Confirm new password: ")
            if pwd != pwd2:
                sys.exit("Passwords do not match.")
            await service.reset_password(acc.id, pwd)
            print(f"Password reset for {args.username}. All active sessions revoked.")

        elif args.command == "disable":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.username.casefold())
            if not acc:
                sys.exit(f"User {args.username} not found")
            await service.disable(acc.id)
            print(f"Account {args.username} disabled.")

        elif args.command == "enable":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.username.casefold())
            if not acc:
                sys.exit(f"User {args.username} not found")
            await service.enable(acc.id)
            print(f"Account {args.username} enabled.")

        elif args.command == "revoke-sessions":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.username.casefold())
            if not acc:
                sys.exit(f"User {args.username} not found")
            await service.revoke_sessions(acc.id)
            print(f"Sessions revoked for {args.username}.")

        elif args.command == "list":
            accounts = await service.list_accounts()
            print(f"{'ID':<38} {'Username':<20} {'Status':<12} {'AuthV':<6} {'RunV':<6}")
            print("-" * 84)
            for a in accounts:
                print(f"{str(a.id):<38} {a.username_display:<20} {a.status.value:<12} {a.auth_version:<6} {a.run_version:<6}")

        elif args.command == "preview-legacy":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.target_username.casefold())
            if not acc:
                sys.exit(f"Target user {args.target_username} not found")
            legacy = LegacyOwnershipService(db_manager._engine)
            manifest = await legacy.preview(acc.id)
            print(f"Manifest ID: {manifest.manifest_id}")
            print(f"Source Digest: {manifest.source_digest}")
            print(f"Records: {manifest.records_count}")

        elif args.command == "apply-legacy":
            async with factory() as uow:
                acc = await uow.accounts.find_login(args.target_username.casefold())
            if not acc:
                sys.exit(f"Target user {args.target_username} not found")
            legacy = LegacyOwnershipService(db_manager._engine)
            manifest = await legacy.preview(acc.id)
            report = await legacy.apply(manifest, args.digest)
            print(f"Applied successfully: {report.records_updated}")

    finally:
        await hasher.shutdown()
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(run_cli())
