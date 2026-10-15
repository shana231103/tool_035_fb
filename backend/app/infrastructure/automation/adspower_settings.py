# File: backend/app/infrastructure/automation/adspower_settings.py
import os
from pathlib import Path
from uuid import UUID
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdsPowerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADSPOWER_", extra="ignore")
    api_base_url: str = "http://127.0.0.1:50325"
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    provider_binding_id: UUID | None = None
    group_id: str = ""
    max_profile_sessions: int = Field(1, ge=1, le=10)
    api_rps: float = Field(1, gt=0, le=20)
    connect_timeout: float = Field(3, gt=0, le=30)
    read_timeout: float = Field(10, gt=0, le=60)
    create_timeout: float = Field(20, gt=0, le=120)
    start_timeout: float = Field(30, gt=0, le=120)
    cdp_timeout: float = Field(15, gt=0, le=60)
    acquire_timeout: float = Field(60, gt=0, le=300)
    resource_wait_timeout: float = Field(30, gt=0, le=300)
    cleanup_timeout: float = Field(30, gt=0, le=120)
    shutdown_timeout: float = Field(60, gt=0, le=300)
    close_timeout: float = Field(5, gt=0, le=30)
    cleanup_attempts: int = Field(3, ge=1, le=10)
    response_limit: int = Field(262144, ge=1024, le=1048576)
    correlation_enabled: bool = False
    correlation_capability_verified: bool = False
    initialize_identity: bool | None = None
    endpoint_mode: str = "SAME_HOST"
    cdp_source_host: str = "127.0.0.1"
    cdp_target_host: str = ""
    debug_port_min: int = Field(1024, ge=1, le=65535)
    debug_port_max: int = Field(65535, ge=1, le=65535)
    identity_path: Path = Field(default_factory=lambda: Path(os.getenv(
        "LOCALAPPDATA", Path.home() / ".local" / "share")) / "ToolReportFB" / "browser-identity.json")

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.debug_port_max < self.debug_port_min:
            raise ValueError("Invalid debug port range")
        if self.endpoint_mode not in {"SAME_HOST", "PRIVATE_REMOTE"}:
            raise ValueError("Invalid browser endpoint mode")
        if self.correlation_enabled and not self.correlation_capability_verified:
            raise ValueError("Correlation capability evidence required")
        return self

    def configured(self) -> bool:
        return bool(self.group_id.strip())
