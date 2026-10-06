# File: backend/app/infrastructure/persistence/repositories/__init__.py
from app.infrastructure.persistence.repositories.postgres_job_repo import PostgresJobRepository
from app.infrastructure.persistence.repositories.postgres_profile_repo import PostgresProfileRepository
from app.infrastructure.persistence.repositories.postgres_proxy_repo import PostgresProxyRepository
from app.infrastructure.persistence.repositories.postgres_task_repo import PostgresTaskRepository

__all__ = [
    "PostgresJobRepository",
    "PostgresTaskRepository",
    "PostgresProxyRepository",
    "PostgresProfileRepository",
]
