"""Lifecycle-only public client."""

from types import TracebackType
from typing import Self

from .config import ConfigManagerConfig
from .exceptions import ConfigurationError, LifecycleError
from .transport import ProviderTransport


class ConfigManager:
    """Synchronous configuration and lifecycle composition root.

    Construction performs local work only. Provider operations are not yet
    implemented. By default, callers retain ownership of injected transports.
    """

    __slots__ = ("_closed", "_config", "_own_transport", "_transport")

    def __init__(
        self,
        server: str | None = None,
        *,
        verify_tls: bool = True,
        transport: ProviderTransport | None = None,
        own_transport: bool = False,
    ) -> None:
        """Create a client without performing remote I/O."""
        if transport is None:
            if server is None:
                raise ConfigurationError("server or transport is required")
            if own_transport:
                raise ConfigurationError("own_transport requires an injected transport")
            self._config: ConfigManagerConfig | None = ConfigManagerConfig(
                server=server, verify_tls=verify_tls
            )
        else:
            if server is not None or verify_tls is not True:
                raise ConfigurationError(
                    "transport is mutually exclusive with AdminService configuration"
                )
            self._config = None
        self._transport = transport
        self._own_transport = own_transport
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return whether the client has been closed."""
        return self._closed

    @property
    def config(self) -> ConfigManagerConfig | None:
        """Return immutable built-in configuration, if configured."""
        self._require_open()
        return self._config

    def _require_open(self) -> None:
        """Reject operations on a closed client."""
        if self._closed:
            raise LifecycleError("ConfigManager is closed")

    def close(self) -> None:
        """Close resources owned by this client; repeated calls are harmless."""
        if self._closed:
            return
        self._closed = True
        if self._own_transport and self._transport is not None:
            self._transport.close()

    def __enter__(self) -> Self:
        """Enter the synchronous client context."""
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client on context exit."""
        self.close()

    def __repr__(self) -> str:
        """Return a minimal representation containing no auth or transport repr."""
        server = self._config.server if self._config is not None else None
        return f"ConfigManager(server={server!r}, closed={self._closed!r})"
