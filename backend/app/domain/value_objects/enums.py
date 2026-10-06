# File: backend/app/domain/value_objects/enums.py
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_EMAIL_SLOT = "WAITING_EMAIL_SLOT"
    WAITING_EMAIL_CODE = "WAITING_EMAIL_CODE"
    VERIFYING_EMAIL = "VERIFYING_EMAIL"
    SUBMITTING = "SUBMITTING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProxyCountry(str, Enum):
    SG = "SG"
    AU = "AU"
    JO = "JO"
    JP = "JP"
    KR = "KR"


class ProxyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEAD = "DEAD"
    TESTING = "TESTING"


class PlatformType(str, Enum):
    FACEBOOK = "FACEBOOK"
    INSTAGRAM = "INSTAGRAM"
    THREADS = "THREADS"
    UNKNOWN = "UNKNOWN"


class ViolationType(str, Enum):
    REPRODUCTION = "reproduction"
    PHOTO = "photo"
    VIDEO = "video"
    POST = "post"
    REEL = "reel"


class OwnerRole(str, Enum):
    OWNER = "OWNER"
    AUTHORIZED_REPRESENTATIVE = "AUTHORIZED_REPRESENTATIVE"
