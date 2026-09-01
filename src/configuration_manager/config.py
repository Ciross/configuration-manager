"""Immutable local configuration values."""

import re
from dataclasses import dataclass

from .exceptions import ConfigurationError

_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def _normalize_server(value: str) -> str:
    """Validate and normalize a simple AdminService DNS host name."""
    if not value or value != value.strip():
        raise ConfigurationError("server must be a non-empty host name")
    # Keeping this explicit prevents URL syntax from being accepted accidentally.
    if any(character in value for character in ":/@?#\\"):
        raise ConfigurationError(
            "server must be a host name without scheme, port, credentials, or path"
        )
    labels = value.split(".")
    if len(value) > 253 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise ConfigurationError("server must be a valid ASCII DNS host name")
    return value.lower()


@dataclass(frozen=True, slots=True)
class ConfigManagerConfig:
    """Validated, non-networked configuration for an AdminService client.

    ``server`` is a host name and implicitly identifies HTTPS. Advanced base URL,
    timeout, and authentication settings are deferred until their transport
    integration contracts can be validated.
    """

    server: str
    verify_tls: bool = True

    def __post_init__(self) -> None:
        """Perform local structural validation and normalize the host."""
        object.__setattr__(self, "server", _normalize_server(self.server))
