# File: backend/migration_support/repair_manifest.py
"""Frozen manifest specification for 006_single_task_repair migration."""

REVISION_006: str = "006_single_task_repair"
DOWN_REVISION_006: str = "005_single_task_execution"

REPAIR_REQUIRED_TABLES = (
    "operator_accounts",
    "operator_sessions",
    "owner_profiles",
    "proxies",
    "proxy_owner_refs",
    "batch_jobs",
    "report_tasks",
    "browser_runtime_bindings",
    "browser_session_leases",
    "operator_artifacts",
    "task_artifact_links",
    "task_start_receipts",
    "task_control_receipts",
    "task_execution_slot",
    "legacy_task_metadata",
)
