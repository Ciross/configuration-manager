"""Strongly typed foundations for Microsoft Configuration Manager."""

from .client import ConfigManager
from .exceptions import (
    AmbiguousResultError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConfigurationManagerError,
    LifecycleError,
    MethodInvocationError,
    NotFoundError,
    QueryError,
    ServerError,
    TLSVerificationError,
    TransportConnectionError,
    TransportError,
    TransportTimeoutError,
)
from .models import Device
from .pagination import Page

__all__ = (
    "AmbiguousResultError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigManager",
    "ConfigurationError",
    "ConfigurationManagerError",
    "Device",
    "LifecycleError",
    "MethodInvocationError",
    "NotFoundError",
    "Page",
    "QueryError",
    "ServerError",
    "TLSVerificationError",
    "TransportConnectionError",
    "TransportError",
    "TransportTimeoutError",
)
