"""Mocked integration coverage for the AdminService HTTP boundary."""

# Internal boundary usage is intentional in integration tests.
# pyright: reportPrivateUsage=false

import ssl

import httpx
import pytest

from configuration_manager import (
    AuthenticationError,
    AuthorizationError,
    LifecycleError,
    ServerError,
    TLSVerificationError,
    TransportConnectionError,
    TransportTimeoutError,
)
from configuration_manager.adminservice import (
    AdminService,
    _AdminServiceHTTPStatusError,
    _AdminServiceResponseError,
    _system_ssl_context,
)
from configuration_manager.transport import AdminServiceSurface


def service(handler: httpx.MockTransport) -> AdminService:
    """Build a verified-configuration service over a controlled transport."""
    return AdminService("cm01.contoso.com", transport=handler)


@pytest.mark.integration
def test_urls_and_query_encoding_are_deterministic() -> None:
    admin = service(httpx.MockTransport(lambda _request: httpx.Response(200)))
    assert str(admin.url(AdminServiceSurface.V1)) == (
        "https://cm01.contoso.com/AdminService/v1.0/"
    )
    assert str(admin.url(AdminServiceSurface.WMI, "SMS_R_System")) == (
        "https://cm01.contoso.com/AdminService/wmi/SMS_R_System"
    )
    url = admin.url(
        AdminServiceSurface.WMI,
        "SMS_R_System",
        params={"$filter": "Name eq 'A B%'"},
    )
    assert url.params["$filter"] == "Name eq 'A B%'"
    assert "%2525" not in str(url)
    admin.close()


@pytest.mark.integration
def test_system_tls_context_verifies_certificates_and_hostnames() -> None:
    context = _system_ssl_context()
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.integration
def test_redirects_are_not_followed() -> None:
    requests: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302, headers={"location": "https://evil.example/private-target"}
        )

    admin = service(httpx.MockTransport(redirect))
    with pytest.raises(_AdminServiceHTTPStatusError, match="HTTP 302") as caught:
        admin.get_json(
            AdminServiceSurface.V1,
            "$metadata",
            params={"$filter": "sensitive=value"},
        )
    assert len(requests) == 1
    assert requests[0].url.host == "cm01.contoso.com"
    assert "evil.example" not in str(caught.value)
    assert "sensitive" not in str(caught.value)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationError),
        (403, AuthorizationError),
        (500, ServerError),
        (503, ServerError),
        (404, _AdminServiceHTTPStatusError),
    ],
)
def test_status_translation(status: int, error: type[Exception]) -> None:
    admin = service(
        httpx.MockTransport(lambda _request: httpx.Response(status, text="secret"))
    )
    with pytest.raises(error) as caught:
        admin.get_json(
            AdminServiceSurface.V1, "operation", params={"$filter": "private=value"}
        )
    assert "secret" not in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("failure", "translated"),
    [
        (httpx.ConnectError("internal details"), TransportConnectionError),
        (httpx.ReadTimeout("internal details"), TransportTimeoutError),
    ],
)
def test_transport_failure_translation(
    failure: httpx.HTTPError, translated: type[Exception]
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        failure.request = request
        raise failure

    admin = service(httpx.MockTransport(fail))
    with pytest.raises(translated) as caught:
        admin.get_json(AdminServiceSurface.WMI, "Anything")
    assert caught.value.__cause__ is failure
    assert "internal details" not in str(caught.value)


@pytest.mark.integration
def test_certificate_failure_translation() -> None:
    certificate_error = ssl.SSLCertVerificationError("certificate details")
    failure = httpx.ConnectError("connect details")
    failure.__cause__ = certificate_error

    def fail(request: httpx.Request) -> httpx.Response:
        failure.request = request
        raise failure

    admin = service(httpx.MockTransport(fail))
    with pytest.raises(TLSVerificationError) as caught:
        admin.get_json(AdminServiceSurface.V1, "Anything")
    assert caught.value.__cause__ is failure


@pytest.mark.integration
def test_json_decoding_size_guard_and_idempotent_cleanup() -> None:
    malformed = service(
        httpx.MockTransport(lambda _request: httpx.Response(200, content=b"{"))
    )
    with pytest.raises(_AdminServiceResponseError) as caught:
        malformed.get_json(AdminServiceSurface.V1, "Anything")
    assert isinstance(caught.value.__cause__, ValueError)
    malformed.close()
    malformed.close()
    assert malformed.closed

    oversized = service(
        httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"x" * (10 * 1024 * 1024 + 1))
        )
    )
    with pytest.raises(_AdminServiceResponseError, match="safety limit"):
        oversized.get_json(AdminServiceSurface.V1, "Anything")


@pytest.mark.integration
@pytest.mark.parametrize("operation", ["json", "text"])
def test_requests_after_close_raise_lifecycle_error(operation: str) -> None:
    requests: list[httpx.Request] = []
    admin = service(
        httpx.MockTransport(
            lambda request: (requests.append(request), httpx.Response(200))[1]
        )
    )
    admin.close()
    admin.close()

    with pytest.raises(LifecycleError, match="closed"):
        if operation == "json":
            admin.get_json(AdminServiceSurface.V1, "Anything")
        else:
            admin.get_text(AdminServiceSurface.V1, "$metadata")
    assert requests == []


@pytest.mark.integration
def test_construction_sends_no_request() -> None:
    requests: list[httpx.Request] = []
    admin = service(
        httpx.MockTransport(
            lambda request: (requests.append(request), httpx.Response(200))[1]
        )
    )
    assert requests == []
    admin.close()
