# File: backend/app/domain/exceptions/operator_errors.py
"""Typed exceptions for operator authentication and tenancy boundaries."""

from typing import Optional


class OperatorError(Exception):
    """Base error for operator domain."""

    def __init__(self, message: str, code: str = "OPERATOR_ERROR"):
        super().__init__(message)
        self.code = code
        self.message = message


class AuthenticationRequiredError(OperatorError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="AUTH_REQUIRED")


class SessionExpiredError(OperatorError):
    def __init__(self, message: str = "Session has expired"):
        super().__init__(message, code="SESSION_EXPIRED")


class SessionRevokedError(OperatorError):
    def __init__(self, message: str = "Session has been revoked"):
        super().__init__(message, code="SESSION_REVOKED")


class InvalidCredentialsError(OperatorError):
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, code="INVALID_CREDENTIALS")


class StaleLoginProofError(OperatorError):
    def __init__(self, message: str = "Login proof is stale"):
        super().__init__(message, code="STALE_LOGIN_PROOF")


class AccountDisabledError(OperatorError):
    def __init__(self, message: str = "Account is disabled"):
        super().__init__(message, code="ACCOUNT_DISABLED")


class OwnedResourceNotFoundError(OperatorError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="OWNED_RESOURCE_MISSING")


class ActiveJobConflictError(OperatorError):
    def __init__(self, message: str = "Account already has an active running job"):
        super().__init__(message, code="ACTIVE_JOB_CONFLICT")


class IngressDeniedError(OperatorError):
    def __init__(self, message: str = "Ingress policy rejected request"):
        super().__init__(message, code="INGRESS_DENIED")


class CsrfInvalidError(OperatorError):
    def __init__(self, message: str = "CSRF token invalid or missing"):
        super().__init__(message, code="CSRF_INVALID")


class HashBusyError(OperatorError):
    def __init__(self, message: str = "Password hashing capacity busy"):
        super().__init__(message, code="HASH_BUSY")


class LoginRateLimitError(OperatorError):
    def __init__(self, message: str = "Too many login attempts", retry_after: int = 60):
        super().__init__(message, code="LOGIN_LIMITED")
        self.retry_after = retry_after


class OperatorExecutionFenceError(OperatorError):
    def __init__(self, message: str = "Execution fence check failed"):
        super().__init__(message, code="EXECUTION_FENCE_FAILED")


class ControlAdmissionError(OperatorError):
    def __init__(self, message: str = "Control admission rejected"):
        super().__init__(message, code="CONTROL_ADMISSION_REJECTED")


class ProxyPolicyError(OperatorError):
    def __init__(self, message: str = "Proxy violates security policy"):
        super().__init__(message, code="PROXY_POLICY_VIOLATION")
