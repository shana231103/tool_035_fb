# File: backend/migration_support/task_start_contract.py
"""Provider-independent audit for the task Start contract forward migration."""
import hashlib
import json
import sqlalchemy as sa

START_CHECK = "(authority_contract_version = 1 AND outcome_phase IN ('FREE','ADMITTED','RUNNING','DRAINING','RECOVERY_REQUIRED')) OR (authority_contract_version = 2 AND outcome_phase IN ('ADMITTED','RUNNING','DRAINING','FINISHED','RECOVERY_REQUIRED') AND admitted_task_version >= 2 AND slot_generation >= 1 AND run_version >= 1)"
CONTROL_CHECK = "authority_contract_version IN (1,2) AND (authority_contract_version = 1 OR (payload_fingerprint IS NOT NULL AND length(payload_fingerprint) = 64 AND (kind != 'STOP_TASK' OR (expected_task_version IS NOT NULL AND expected_task_version >= 1))))"


def audit_existing(bind):
    checks = {
        "TASK_VERSION": "SELECT count(*) FROM report_tasks WHERE version < 1 OR version IS NULL",
        "SLOT_GENERATION": "SELECT count(*) FROM task_execution_slot WHERE generation < 0",
        "START_CONTRACT": f"SELECT count(*) FROM task_start_receipts WHERE NOT ({START_CHECK})",
        "ARTIFACT_RESOURCE": "SELECT count(*) FROM operator_artifacts WHERE job_id IS NULL AND task_id IS NULL",
        "ARTIFACT_OWNER": "SELECT count(*) FROM operator_artifacts a LEFT JOIN report_tasks t ON a.task_id=t.id AND a.operator_account_id=t.operator_account_id WHERE a.task_id IS NOT NULL AND t.id IS NULL",
        "ARTIFACT_LINK": "SELECT count(*) FROM task_artifact_links l LEFT JOIN operator_artifacts a ON l.artifact_id=a.id AND l.operator_account_id=a.operator_account_id AND l.kind=a.kind WHERE a.id IS NULL",
    }
    violations = [code for code, query in checks.items() if bind.execute(sa.text(query)).scalar()]
    if violations:
        raise RuntimeError("Task Start migration audit failed: " + ",".join(violations))
    return evidence_snapshot(bind)


def evidence_snapshot(bind):
    projections = {
        "tasks": "SELECT id,operator_account_id,status,version,attempt_id,submitted_at,receipt_text,meta_case_number,screenshot_path FROM report_tasks ORDER BY id",
        "receipts": "SELECT operator_account_id,command_id,task_id,attempt_id,slot_generation,run_version,runtime_epoch,admitted_task_version,admitted_at,payload_fingerprint,authority_contract_version,outcome_phase FROM task_start_receipts ORDER BY operator_account_id,command_id",
        "ledger": "SELECT operation_id,task_id,attempt_id,charged FROM browser_session_leases ORDER BY operation_id",
        "artifacts": "SELECT id,operator_account_id,job_id,task_id,kind,storage_key FROM operator_artifacts ORDER BY id",
    }
    result = {}
    for key, query in projections.items():
        rows = [tuple(str(v) if v is not None else None for v in row) for row in bind.execute(sa.text(query))]
        result[key] = (len(rows), hashlib.sha256(json.dumps(rows).encode()).hexdigest())
    return result


def verify_preserved(bind, before):
    if evidence_snapshot(bind) != before:
        raise RuntimeError("Task Start migration changed existing evidence or ownership.")
    if bind.dialect.name == "sqlite" and bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall():
        raise RuntimeError("Task Start migration foreign key audit failed.")
