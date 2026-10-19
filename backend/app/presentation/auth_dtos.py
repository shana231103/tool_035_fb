# File: backend/app/presentation/auth_dtos.py
"""Pydantic schemas for operator login and session representation."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.operator_records import SessionView


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=12, max_length=1024)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Username cannot be blank")
        return s


class OperatorInfoResponse(BaseModel):
    id: str
    username: str


class SessionResponse(BaseModel):
    authenticated: bool
    operator: Optional[OperatorInfoResponse] = None
    session_context: Optional[str] = None
    csrf_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    idle_expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_domain(cls, view: SessionView) -> "SessionResponse":
        op_info = None
        if view.operator:
            op_info = OperatorInfoResponse(
                id=view.operator.get("id", ""),
                username=view.operator.get("username", ""),
            )
        return cls(
            authenticated=view.authenticated,
            operator=op_info,
            session_context=str(view.session_context) if view.session_context else None,
            csrf_token=view.csrf_token,
            expires_at=view.expires_at,
            idle_expires_at=view.idle_expires_at,
        )
