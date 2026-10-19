# File: backend/app/infrastructure/persistence/database_connection.py
"""Shared async engine configuration for runtime and migration connections."""
from __future__ import annotations

import ipaddress
import ssl
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool


def _is_loopback(host: str | None) -> bool:
    if host and host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def _tls_options(url: URL) -> tuple[URL, dict[str, Any]]:
    """Translate libpq URI flags; asyncpg does not accept sslmode as a kwarg."""
    choices: list[bool] = []
    for key in ("sslmode", "ssl"):
        values = url.normalized_query.get(key, ())
        for value in values:
            value = value.lower()
            if value in {"require", "verify-ca", "verify-full", "true", "1", "on"}:
                choices.append(True)
            elif value in {"disable", "false", "0", "off"}:
                choices.append(False)
            else:
                raise ValueError("Unsupported database TLS option; use verify-full or disable locally.")
    if len(set(choices)) > 1:
        raise ValueError("Conflicting database TLS options.")
    enabled = choices[0] if choices else True
    if not enabled and not _is_loopback(url.host):
        raise ValueError("Remote PostgreSQL connections require verified TLS.")
    # Certificate file flags would otherwise leak into asyncpg's keyword args.
    if any(key in url.query for key in ("sslcert", "sslkey", "sslrootcert")):
        raise ValueError("Configure the trusted CA through SSL_CERT_FILE; URI certificate flags are unsupported.")
    url = url.difference_update_query(("sslmode", "ssl"))
    context = ssl.create_default_context() if enabled else False
    host = (url.host or "").lower().rstrip(".")
    if enabled and host.endswith((".supabase.co", ".pooler.supabase.com")):
        # Supabase's private root is not in the public OS trust store. Read PEM
        # through Python: OpenSSL SSL_CERT_FILE can fail on Windows Unicode paths.
        ca = Path(__file__).resolve().parents[3] / "certs" / "supabase-root.crt"
        context.load_verify_locations(cadata=ca.read_text(encoding="utf-8"))
        # Supabase Intermediate 2021 lacks Key Usage (supabase/supabase#50862).
        # Use normal OpenSSL chain validation as on Python <=3.12. CA signatures,
        # certificate validity and hostname verification remain required.
        context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return url, {"ssl": context}


def build_async_engine_options(
    db_url: str, *, echo: bool = False, migration: bool = False
) -> tuple[URL, dict[str, Any]]:
    """Return a normalized URL and safe SQLAlchemy create_async_engine kwargs.

    Migration connections use NullPool. Direct/session pooling are supported.
    Transaction pooling needs separate asyncpg prepared-statement configuration.
    Credentials are deliberately excluded from all configuration error messages.
    """
    try:
        url = make_url(db_url)
        # Validate port here, so SQLAlchemy's parsing error cannot expose input.
        port = url.port
    except Exception:
        raise ValueError("Invalid database connection URL.") from None
    options: dict[str, Any] = {"echo": echo, "future": True, "pool_pre_ping": True}
    if url.drivername in {"sqlite", "sqlite+aiosqlite"}:
        return url.set(drivername="sqlite+aiosqlite"), {
            **options, "connect_args": {"check_same_thread": False},
        }
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("Use a PostgreSQL asyncpg URL or an async SQLite URL.")
    if not url.host or not url.database:
        raise ValueError("PostgreSQL URL requires a hostname and database name.")
    if set(url.query) - {"ssl", "sslmode"}:
        # asyncpg dialect query arguments override authority host/port/user.
        # Keep the destination used for policy validation authoritative.
        raise ValueError("Only ssl and sslmode PostgreSQL URL query options are supported.")
    if port == 6543:
        raise ValueError("Transaction pooler port 6543 is unsupported; use direct or session pooler port 5432.")
    url, connect_args = _tls_options(url.set(drivername="postgresql+asyncpg"))
    options["connect_args"] = {**connect_args, "timeout": 15, "command_timeout": 60}
    if migration:
        options["poolclass"] = NullPool
    else:
        options.update(pool_size=5, max_overflow=5, pool_timeout=30, pool_recycle=1800)
    return url, options
