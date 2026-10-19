# File: backend/app/core/config.py
import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, field_validator
from urllib.parse import urlsplit


def _get_default_database_url() -> str:
    custom = os.getenv("DATABASE_URL")
    if custom:
        return custom
    if getattr(sys, "frozen", False):
        app_dir = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ToolReportFB"
        app_dir.mkdir(parents=True, exist_ok=True)
        db_file = (app_dir / "report_fb.db").as_posix()
        return f"sqlite+aiosqlite:///{db_file}"
    return "sqlite+aiosqlite:///./report_fb.db"


def _get_default_storage_dir() -> str:
    custom = os.getenv("STORAGE_DIR")
    if custom:
        return custom
    if getattr(sys, "frozen", False):
        app_dir = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ToolReportFB" / "storage"
        app_dir.mkdir(parents=True, exist_ok=True)
        return str(app_dir)
    return "./storage"


class Settings(BaseSettings):
    app_name: str = "Batch Meta Copyright Reporter"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = Field(default_factory=_get_default_database_url)
    database_migration_url: str | None = None
    database_echo: bool = False

    # Operator deployment & ingress
    operator_deployment_mode: str = Field(
        default="local",
        validation_alias=AliasChoices("OPERATOR_DEPLOYMENT_MODE", "operator_deployment_mode"),
    )
    operator_public_origin: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPERATOR_PUBLIC_ORIGIN", "operator_public_origin"),
    )

    # Storage paths
    base_storage_dir: str = Field(default_factory=_get_default_storage_dir)
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000/static")

    # Automation Engine
    headless_browser: bool = False
    navigation_timeout_ms: int = Field(45000, ge=1000)
    receipt_timeout_ms: int = Field(30000, ge=1000)
    email_verification_timeout: int = Field(900, ge=1)
    email_slot_timeout: int = Field(1800, ge=1)
    max_code_attempts: int = Field(5, ge=1, le=10)
    max_code_resends: int = Field(2, ge=0, le=5)
    max_browser_contexts: int = Field(5, ge=1, le=10)
    anticaptcha_api_key: str = "a31e63ea8e8e9055927db54467a55da9"
    anticaptcha_timeout: float = Field(120.0, ge=10, le=600)

    # Worker queue defaults
    default_concurrency: int = 1
    default_delay_min: int = 0
    default_delay_max: int = 0

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5175", "http://127.0.0.1:5175",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ]
    local_allowed_hosts: list[str] = Field(
        default=[
            "localhost:8000", "127.0.0.1:8000",
            "localhost:5173", "127.0.0.1:5173",
            "localhost:5174", "127.0.0.1:5174",
            "localhost:5175", "127.0.0.1:5175",
        ],
        validation_alias=AliasChoices("LOCAL_ALLOWED_HOSTS", "MAILBOX_ALLOWED_HOSTS", "local_allowed_hosts"),
    )
    max_proof_bytes: int = Field(10485760, ge=1, le=10485760)
    max_proof_pixels: int = Field(20000000, ge=1, le=20000000)
    max_encoded_proof_bytes: int = Field(20971520, ge=1, le=20971520)
    proof_worker_concurrency: int = Field(1, ge=1, le=1)
    ws_max_clients: int = Field(32, ge=1, le=32)
    ws_queue_size: int = Field(32, ge=1, le=32)
    ws_max_payload_bytes: int = Field(65536, ge=1, le=65536)
    ws_send_timeout: float = Field(2.0, gt=0, le=10)
    ws_close_timeout: float = Field(1.0, gt=0, le=5)
    microsoft_authority: str = "https://login.microsoftonline.com/common"
    microsoft_http_timeout: float = Field(10, ge=1, le=10)
    graph_request_budget: int = Field(120, ge=1, le=500)
    graph_page_budget: int = Field(5, ge=1, le=20)
    graph_body_budget: int = Field(10, ge=1, le=50)
    graph_poll_interval: float = Field(5, ge=0.1, le=60)

    @field_validator("cors_origins")
    @classmethod
    def exact_local_origins(cls, values):
        for value in values:
            parsed = urlsplit(value)
            if (parsed.scheme not in ("http", "https") or
                parsed.hostname not in ("localhost", "127.0.0.1", "::1") or
                parsed.path or parsed.query or parsed.fragment or parsed.username or
                parsed.password or parsed.netloc.lower() != parsed.netloc):
                raise ValueError("CORS requires exact local origins.")
            _ = parsed.port
        return values

    @field_validator("local_allowed_hosts")
    @classmethod
    def exact_local_hosts(cls, values):
        for value in values:
            parsed = urlsplit("http://" + value)
            if (parsed.hostname not in ("localhost", "127.0.0.1", "::1") or
                    parsed.netloc != value or value != value.lower() or parsed.username or
                    parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("Host requires exact local authorities.")
            _ = parsed.port
        return values

    @property
    def mailbox_allowed_hosts(self):
        return self.local_allowed_hosts

    @field_validator("microsoft_authority")
    @classmethod
    def trusted_authority(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.netloc != "login.microsoftonline.com" or
                not parsed.path.strip("/") or parsed.query or parsed.fragment):
            raise ValueError("Microsoft authority must use the trusted HTTPS login host.")
        return value

    @field_validator("operator_deployment_mode")
    @classmethod
    def validate_deployment_mode(cls, value: str) -> str:
        clean = (value or "local").lower().strip()
        if clean not in ("local", "hosted"):
            raise ValueError("OPERATOR_DEPLOYMENT_MODE must be 'local' or 'hosted'.")
        return clean

    @field_validator("operator_public_origin")
    @classmethod
    def validate_public_origin(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip().rstrip("/")
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError(
                    "OPERATOR_PUBLIC_ORIGIN must be a canonical HTTPS URL (e.g. https://domain[:port])."
                )
        return value

    model_config = SettingsConfigDict(
        env_file=(
            Path(sys.executable).resolve().parent / ".env",
            Path(__file__).resolve().parents[3] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
