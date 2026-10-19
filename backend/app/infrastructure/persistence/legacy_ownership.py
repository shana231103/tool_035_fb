# File: backend/app/infrastructure/persistence/legacy_ownership.py
"""Service for offline preview and assignment of legacy quarantined data."""

from datetime import datetime, timezone
import hashlib
from typing import Dict, Optional
from uuid import UUID, uuid4
import sqlalchemy as sa

from app.application.operator_records import AssignmentManifest, AssignmentReport
from app.domain.exceptions.operator_errors import OperatorError


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyOwnershipService:
    """Manages offline connected-graph preview and atomic migration from quarantine."""

    def __init__(self, db_engine):
        self._engine = db_engine

    def _get_quarantine_id(self, conn) -> Optional[str]:
        res = conn.execute(
            sa.text(
                "SELECT id FROM operator_accounts WHERE status = 'QUARANTINED' LIMIT 1"
            )
        ).scalar()
        return str(res) if res else None

    def _compute_digest(self, records: Dict[str, list[str]]) -> str:
        hasher = hashlib.sha256()
        for key in sorted(records.keys()):
            for item in sorted(records[key]):
                hasher.update(f"{key}:{item}\n".encode("utf-8"))
        return hasher.hexdigest()

    async def preview(self, target_account_id: UUID) -> AssignmentManifest:
        def _sync_preview(conn):
            qid = self._get_quarantine_id(conn)
            if not qid:
                raise OperatorError("No quarantined account found in database")

            target_valid = conn.execute(
                sa.text(
                    "SELECT 1 FROM operator_accounts WHERE id = :id AND status != 'QUARANTINED'"
                ),
                {"id": str(target_account_id)},
            ).scalar()
            if not target_valid:
                raise OperatorError(f"Target account {target_account_id} not valid")

            records: Dict[str, list[str]] = {}
            counts: Dict[str, int] = {}
            for tbl in ("owner_profiles", "proxies", "batch_jobs", "report_tasks"):
                ids = conn.execute(
                    sa.text(
                        f"SELECT id FROM {tbl} WHERE operator_account_id = :qid ORDER BY id"
                    ),
                    {"qid": qid},
                ).scalars().all()
                records[tbl] = [str(x) for x in ids]
                counts[tbl] = len(ids)

            digest = self._compute_digest(records)
            return AssignmentManifest(
                manifest_id=uuid4(),
                target_account_id=target_account_id,
                schema_version="004_operator_accounts",
                components_count=counts.get("batch_jobs", 0),
                records_count=counts,
                source_digest=digest,
                created_at=_now(),
            )

        async with self._engine.connect() as conn:
            return await conn.run_sync(_sync_preview)

    async def apply(
        self, manifest: AssignmentManifest, expected_digest: str
    ) -> AssignmentReport:
        if manifest.source_digest != expected_digest:
            raise OperatorError("Manifest digest mismatch. Operation rejected.")

        def _sync_apply(conn):
            qid = self._get_quarantine_id(conn)
            if not qid:
                raise OperatorError("No quarantined account found")

            # Check target
            target_str = str(manifest.target_account_id)
            target_valid = conn.execute(
                sa.text(
                    "SELECT 1 FROM operator_accounts WHERE id = :id AND status != 'QUARANTINED'"
                ),
                {"id": target_str},
            ).scalar()
            if not target_valid:
                raise OperatorError(f"Target account {target_str} not valid")

            # Verify current digest before updating
            records: Dict[str, list[str]] = {}
            for tbl in ("owner_profiles", "proxies", "batch_jobs", "report_tasks"):
                ids = conn.execute(
                    sa.text(
                        f"SELECT id FROM {tbl} WHERE operator_account_id = :qid ORDER BY id"
                    ),
                    {"qid": qid},
                ).scalars().all()
                records[tbl] = [str(x) for x in ids]

            current_digest = self._compute_digest(records)
            if current_digest != expected_digest:
                raise OperatorError("Database changed since preview. Apply rejected.")

            updated_counts = {}
            for tbl in ("owner_profiles", "proxies", "batch_jobs", "report_tasks"):
                res = conn.execute(
                    sa.text(
                        f"UPDATE {tbl} SET operator_account_id = :tid WHERE operator_account_id = :qid"
                    ),
                    {"tid": target_str, "qid": qid},
                )
                updated_counts[tbl] = res.rowcount

            # Update proxy owner refs
            res_refs = conn.execute(
                sa.text(
                    "UPDATE proxy_owner_refs SET operator_account_id = :tid WHERE operator_account_id = :qid"
                ),
                {"tid": target_str, "qid": qid},
            )
            updated_counts["proxy_owner_refs"] = res_refs.rowcount

            # Check SQLite foreign keys
            if conn.dialect.name == "sqlite":
                fk_violations = conn.execute(
                    sa.text("PRAGMA foreign_key_check")
                ).fetchall()
                if fk_violations:
                    raise OperatorError(f"FK check failed on apply: {fk_violations}")

            return AssignmentReport(
                manifest_id=manifest.manifest_id,
                applied_at=_now(),
                records_updated=updated_counts,
                status="APPLIED",
            )

        async with self._engine.begin() as conn:
            return await conn.run_sync(_sync_apply)
