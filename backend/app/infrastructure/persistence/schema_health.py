# File: backend/app/infrastructure/persistence/schema_health.py
from sqlalchemy import inspect
from app.domain.value_objects.enums import JobStatus, TaskStatus


async def check_schema(manager) -> None:
    def verify(connection):
        inspector = inspect(connection)
        required = {
            "owner_profiles": {"rights_owner_name", "sender_name", "rights_jurisdiction", "owner_role"},
            "report_tasks": {"attempt_id", "input_snapshot", "verification", "submitted_at", "receipt_text"},
        }
        for table, fields in required.items():
            names = {column["name"] for column in inspector.get_columns(table)}
            if not fields <= names:
                raise RuntimeError("Database needs migration: run python -m alembic -c backend/alembic.ini upgrade head.")
    await manager.validate_schema(verify)


async def recover_interrupted(factory) -> None:
    active = {TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_SLOT,
              TaskStatus.WAITING_EMAIL_CODE, TaskStatus.VERIFYING_EMAIL, TaskStatus.SUBMITTING}
    offset = 0
    while True:
        async with factory() as uow:
            jobs = await uow.jobs.list_jobs(limit=100, offset=offset)
            for job in jobs:
                changed = False
                for task in job.tasks:
                    if task.status in active:
                        task.mark_failed("Browser session lost on restart. No automatic resume.", False)
                        task.verification = {}
                        await uow.tasks.save(task)
                        changed = True
                if changed or job.status == JobStatus.RUNNING:
                    job.pause()
                    await uow.jobs.save(job)
        if len(jobs) < 100:
            break
        offset += 100
