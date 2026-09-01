"""Public exception hierarchy for the SDK."""


class ConfigurationManagerError(Exception):
    """Base class for all SDK-defined errors."""


class ConfigurationError(ConfigurationManagerError):
    """Raised when local SDK configuration is invalid."""


class LifecycleError(ConfigurationManagerError):
    """Raised when an operation is incompatible with the client lifecycle."""


class TransportError(ConfigurationManagerError):
    """Base class for provider transport failures."""


class TransportConnectionError(TransportError):
    """Raised when a transport cannot establish a connection."""


class TransportTimeoutError(TransportError):
    """Raised when a transport operation times out."""


class TLSVerificationError(TransportError):
    """Raised when TLS peer verification fails."""


class ResponseError(TransportError):
    """Raised when an HTTP response cannot be safely consumed."""


class HTTPStatusError(TransportError):
    """Raised for an HTTP status that needs operation-level interpretation."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(ConfigurationManagerError):
    """Raised when authentication fails or is unavailable."""


class AuthorizationError(ConfigurationManagerError):
    """Raised when the provider denies an operation."""


class QueryError(ConfigurationManagerError):
    """Raised when a provider query is invalid or fails."""


class MethodInvocationError(ConfigurationManagerError):
    """Raised when a provider method invocation fails."""


class ServerError(ConfigurationManagerError):
    """Raised for an otherwise unclassified provider failure."""


class NotFoundError(ConfigurationManagerError):
    """Raised when a requested SDK resource is not found."""


class AmbiguousResultError(ConfigurationManagerError):
    """Raised when an operation requiring one result finds more than one."""
