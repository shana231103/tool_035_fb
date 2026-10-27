# File: backend/app/domain/exceptions/domain_exceptions.py
class DomainError(Exception):
    """Base domain exception."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidMetaUrlError(DomainError):
    """Raised when URL is not a recognized Meta platform resource."""


class InvalidOriginalUrlError(DomainError):
    """Raised when original proof URL is invalid, relative, or points to localhost/private IP."""


class InvalidEmailError(DomainError):
    """Raised when email address syntax is invalid."""


class InvalidProxyError(DomainError):
    """Raised when proxy string or configuration is invalid."""


class InvalidStateTransitionError(DomainError):
    """Raised when an illegal lifecycle transition occurs."""


class EntityNotFoundError(DomainError):
    """Raised when an entity requested from repository does not exist."""
