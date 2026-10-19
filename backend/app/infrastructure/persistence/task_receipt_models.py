# File: backend/app/infrastructure/persistence/task_receipt_models.py
"""Versioned task command receipt ORM declarations."""
from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, CheckConstraint
from app.infrastructure.persistence.database import Base

class TaskStartReceiptModel(Base):
    __tablename__ = "task_start_receipts"

    operator_account_id = Column(
        String(36), ForeignKey("operator_accounts.id"), primary_key=True
    )
    command_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), nullable=False)
    attempt_id = Column(String(36), nullable=False)
    slot_generation = Column(Integer, nullable=False)
    run_version = Column(Integer, nullable=False)
    runtime_epoch = Column(String(36), nullable=False)
    admitted_task_version = Column(Integer, nullable=False)
    admitted_at = Column(DateTime(timezone=True), nullable=False)
    payload_fingerprint = Column(Text, nullable=False)
    authority_contract_version = Column(Integer, nullable=False, default=2, server_default="1")
    outcome_phase = Column(String(30), nullable=False, default="ADMITTED")

    __table_args__ = (
        CheckConstraint("(authority_contract_version = 1 AND outcome_phase IN ('FREE','ADMITTED','RUNNING','DRAINING','RECOVERY_REQUIRED')) OR (authority_contract_version = 2 AND outcome_phase IN ('ADMITTED','RUNNING','DRAINING','FINISHED','RECOVERY_REQUIRED') AND admitted_task_version >= 2 AND slot_generation >= 1 AND run_version >= 1)", name="ck_start_receipt_contract"),
        ForeignKeyConstraint(
            ["task_id", "operator_account_id"],
            ["report_tasks.id", "report_tasks.operator_account_id"],
            name="fk_start_receipts_task_owner",
        ),
        Index(
            "ix_task_start_receipts_task",
            "task_id",
            "operator_account_id",
            "admitted_at",
        ),
    )


class TaskControlReceiptModel(Base):
    __tablename__ = "task_control_receipts"

    operator_account_id = Column(
        String(36), ForeignKey("operator_accounts.id"), primary_key=True
    )
    command_id = Column(String(36), primary_key=True)
    kind = Column(String(50), nullable=False)
    target_id = Column(Text, nullable=False)
    target_generation = Column(Integer, nullable=False)
    initiating_session_id = Column(String(36), nullable=False)
    auth_version = Column(Integer, nullable=False)
    admitted_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(30), nullable=False, default="ADMITTED")
    result_code = Column(String(50), nullable=False, default="ADMITTED")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)


    payload_fingerprint = Column(Text, nullable=True)
    expected_task_version = Column(Integer, nullable=True)
    attempt_id = Column(String(36), nullable=True)
    authority_contract_version = Column(Integer, nullable=False, default=2, server_default="1")
    __table_args__ = (
        CheckConstraint("authority_contract_version IN (1,2) AND (authority_contract_version = 1 OR (payload_fingerprint IS NOT NULL AND length(payload_fingerprint) = 64 AND (kind != 'STOP_TASK' OR (expected_task_version IS NOT NULL AND expected_task_version >= 1))))", name="ck_control_receipt_contract"),
        CheckConstraint("version >= 1", name="ck_control_receipt_version"),
    )
