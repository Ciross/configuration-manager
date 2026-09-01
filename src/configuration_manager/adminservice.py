"""Internal synchronous HTTP boundary for Configuration Manager AdminService."""

from __future__ import annotations

import importlib
import json
import ssl
import sys
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import cast

import httpx
import truststore

from .config import ConfigManagerConfig
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    LifecycleError,
    ServerError,
    TLSVerificationError,
    TransportConnectionError,
    TransportError,
    TransportTimeoutError,
)
from .transport import AdminServiceSurface, JsonValue

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class _AdminServiceResponseError(TransportError):
    """Raised when an AdminService response cannot be safely consumed."""


class _AdminServiceHTTPStatusError(TransportError):
    """Raised for a status requiring later operation-level interpretation."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _system_ssl_context() -> ssl.SSLContext:
    """Create an isolated client context backed by the operating-system store."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def windows_integrated_authentication() -> httpx.Auth:
    """Construct current-credential SSPI Negotiate auth without delegation."""
    if sys.platform != "win32":
        raise RuntimeError("Windows Integrated Authentication requires Windows")
    module = importlib.import_module("httpx_negotiate_sspi")
    constructor = cast("Callable[..., httpx.Auth]", module.HttpSspiAuth)
    return constructor(delegate=False)


def _is_certificate_failure(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        current = current.__cause__ or current.__context__
    return False


class AdminService:
    """Execute bounded AdminService HTTP requests without domain semantics.

    This class is internal while the raw/resource contracts remain unimplemented.
    Construction creates local objects only and never sends a request.
    """

    __slots__ = ("_client", "_closed", "_origin")

    def __init__(
        self,
        server: str,
        *,
        verify_tls: bool = True,
        auth: httpx.Auth | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        config = ConfigManagerConfig(server=server, verify_tls=verify_tls)
        self._origin = httpx.URL(scheme="https", host=config.server)
        verification: ssl.SSLContext | bool = (
            _system_ssl_context() if verify_tls else False
        )
        self._client = httpx.Client(
            verify=verification,
            auth=auth,
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=False,
            transport=transport,
        )
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def url(
        self,
        surface: AdminServiceSurface,
        path: str = "",
        *,
        params: Mapping[str, str] | None = None,
    ) -> httpx.URL:
        """Build one HTTPS AdminService URL, encoding query values once."""
        clean_path = path.lstrip("/")
        url = self._origin.copy_with(path=f"/AdminService/{surface.value}/{clean_path}")
        return url.copy_merge_params(params) if params is not None else url

    def get_json(
        self,
        surface: AdminServiceSurface,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonValue:
        """GET and explicitly decode a bounded JSON response."""
        content = self._get_bytes(surface, path, params=params)
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise _AdminServiceResponseError(
                "AdminService returned malformed JSON"
            ) from error
        return cast("JsonValue", value)

    def get_text(self, surface: AdminServiceSurface, path: str) -> str:
        """GET and decode bounded text, used by the opt-in metadata probe."""
        content = self._get_bytes(surface, path)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _AdminServiceResponseError(
                "AdminService returned invalid UTF-8 text"
            ) from error

    def _get_bytes(
        self,
        surface: AdminServiceSurface,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> bytes:
        self._require_open()
        try:
            with self._client.stream(
                "GET", self.url(surface, path, params=params)
            ) as response:
                self._raise_for_status(response.status_code)
                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise _AdminServiceResponseError(
                            "AdminService response exceeded the safety limit"
                        )
                    content.extend(chunk)
                return bytes(content)
        except _AdminServiceResponseError:
            raise
        except httpx.TimeoutException as error:
            raise TransportTimeoutError("AdminService request timed out") from error
        except httpx.ConnectError as error:
            if _is_certificate_failure(error):
                raise TLSVerificationError(
                    "AdminService TLS certificate verification failed"
                ) from error
            raise TransportConnectionError(
                "Could not connect to AdminService"
            ) from error
        except httpx.HTTPError as error:
            raise TransportError("AdminService HTTP transport failed") from error

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if 300 <= status_code < 400:
            raise _AdminServiceHTTPStatusError(
                f"AdminService returned HTTP {status_code}", status_code=status_code
            )
        if status_code == 401:
            raise AuthenticationError("AdminService authentication failed")
        if status_code == 403:
            raise AuthorizationError("AdminService authorization was denied")
        if status_code >= 500:
            raise ServerError(f"AdminService returned HTTP {status_code}")
        if status_code >= 400:
            raise _AdminServiceHTTPStatusError(
                f"AdminService returned HTTP {status_code}", status_code=status_code
            )

    def _require_open(self) -> None:
        if self._closed:
            raise LifecycleError("AdminService is closed")

    def close(self) -> None:
        """Release pooled connections exactly once."""
        if self._closed:
            return
        self._closed = True
        self._client.close()

    def __enter__(self) -> AdminService:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
