# File: backend/app/application/dtos/proxy_dtos.py
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.domain.value_objects.enums import ProxyCountry, ProxyStatus


class CreateProxyRequestDTO(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    country: ProxyCountry
    protocol: str = Field("http", pattern="^(http|https|socks5)$")
    username: Optional[str] = None
    password: Optional[str] = None


class ProxyResponseDTO(BaseModel):
    id: UUID
    protocol: str
    host: str
    port: int
    country: ProxyCountry
    username: Optional[str] = None
    status: ProxyStatus
    latency_ms: int
    consecutive_failures: int
    created_at: datetime
    last_checked_at: Optional[datetime] = None


class TestProxyResponseDTO(BaseModel):
    proxy_id: UUID
    is_alive: bool
    latency_ms: int
    status: ProxyStatus
    error: Optional[str] = None
