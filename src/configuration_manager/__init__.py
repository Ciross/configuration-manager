"""Strongly typed foundations for Microsoft Configuration Manager."""

from .client import ConfigManager
from .exceptions import (
    AmbiguousResultError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConfigurationManagerError,
    HTTPStatusError,
    LifecycleError,
    MethodInvocationError,
    NotFoundError,
    QueryError,
    ResponseError,
    ServerError,
    TLSVerificationError,
    TransportConnectionError,
    TransportError,
    TransportTimeoutError,
)
from .pagination import Page

__all__ = (
    "AmbiguousResultError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigManager",
    "ConfigurationError",
    "ConfigurationManagerError",
    "HTTPStatusError",
    "LifecycleError",
    "MethodInvocationError",
    "NotFoundError",
    "Page",
    "QueryError",
    "ResponseError",
    "ServerError",
    "TLSVerificationError",
    "TransportConnectionError",
    "TransportError",
    "TransportTimeoutError",
)
