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
from .models import (
    Collection,
    CollectionDeviceMember,
    CollectionType,
    Device,
    DeviceCollectionMembership,
)
from .pagination import Page

__all__ = (
    "AmbiguousResultError",
    "AuthenticationError",
    "AuthorizationError",
    "Collection",
    "CollectionDeviceMember",
    "CollectionType",
    "ConfigManager",
    "ConfigurationError",
    "ConfigurationManagerError",
    "Device",
    "DeviceCollectionMembership",
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
