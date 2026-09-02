"""Controlled HTTP coverage for AdminService WMI collection queries."""

# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import (
    AuthenticationError,
    AuthorizationError,
    ConfigManager,
    QueryError,
    ServerError,
)
from configuration_manager.adminservice import AdminService
from configuration_manager.adminservice_transport import _AdminServiceProviderTransport


def client_with(handler: httpx2.MockTransport) -> ConfigManager:
    return ConfigManager(
        transport=_AdminServiceProviderTransport(
            AdminService("cm01.contoso.com", transport=handler)
        ),
        own_transport=True,
    )


@pytest.mark.integration
def test_query_serializes_options_once_and_parses_envelope() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200, json={"@odata.context": "ignored", "value": [{"Name": "A"}]}
        )

    with client_with(httpx2.MockTransport(respond)) as client:
        page = client.raw.wmi.query(
            "SMS_R_System",
            filter="Name eq 'A B%'",
            select=("ResourceID", "Name"),
            expand=("Resource",),
            order_by=("Name", "ResourceID desc"),
            top=100,
        )
    assert page.items == ({"Name": "A"},)
    assert len(requests) == 1
    assert requests[0].url.path == "/AdminService/wmi/SMS_R_System"
    assert dict(requests[0].url.params) == {
        "$filter": "Name eq 'A B%'",
        "$select": "ResourceID,Name",
        "$expand": "Resource",
        "$orderby": "Name,ResourceID desc",
        "$top": "100",
    }
    assert "%2525" not in str(requests[0].url)


@pytest.mark.integration
def test_raw_record_preserves_adminservice_property_casing() -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200, json={"value": [{"ResourceId": 123, "Name": "PC001"}]}
            )
        )
    )

    page = client.raw.wmi.query("SMS_R_System", select=("ResourceId", "Name"), top=1)

    assert page.items == ({"ResourceId": 123, "Name": "PC001"},)
    assert "ResourceId" in page.items[0]
    assert "ResourceID" not in page.items[0]


@pytest.mark.integration
@pytest.mark.parametrize(
    "body",
    [[], {}, {"value": {}}, {"value": [1]}, {"value": [], "@odata.nextLink": ""}],
)
def test_malformed_envelopes_are_query_errors(body: object) -> None:
    client = client_with(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, json=body))
    )
    with pytest.raises(QueryError):
        client.raw.wmi.query("SMS_R_System")


@pytest.mark.integration
@pytest.mark.parametrize(
    "link",
    [
        "http://cm01.contoso.com/AdminService/wmi/X?$skiptoken=x",
        "https://evil.example/AdminService/wmi/X?$skiptoken=x",
        "https://cm01.contoso.com:8443/AdminService/wmi/X?$skiptoken=x",
        "https://cm01.contoso.com/AdminService/v1.0/X?$skiptoken=x",
        "https://user:pass@cm01.contoso.com/AdminService/wmi/X",
    ],
)
def test_unsafe_continuation_is_rejected_without_second_request(link: str) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"value": [], "@odata.nextLink": link})

    client = client_with(httpx2.MockTransport(respond))
    with pytest.raises(QueryError):
        client.raw.wmi.query("SMS_R_System")
    assert len(requests) == 1


@pytest.mark.integration
def test_continuation_is_followed_exactly_once_and_bound_to_transport() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(
                200,
                json={
                    "value": [{"Page": 1}],
                    "@odata.nextLink": (
                        "/AdminService/wmi/SMS_R_System?$skiptoken=A%2FB%3D"
                    ),
                },
            )
        return httpx2.Response(200, json={"value": [{"Page": 2}]})

    client = client_with(httpx2.MockTransport(respond))
    page = client.raw.wmi.query("SMS_R_System")
    assert page.has_next
    other = client_with(httpx2.MockTransport(respond))
    with pytest.raises(ValueError, match="another transport"):
        other.raw.wmi.next_page(page)
    page = client.raw.wmi.next_page(page)
    assert page.items[0]["Page"] == 2
    assert len(requests) == 2
    assert requests[1].url.query == b"$skiptoken=A%2FB%3D"


@pytest.mark.integration
@pytest.mark.parametrize(
    "link",
    [
        "https://cm01.contoso.com/AdminService/wmi/SMS_R_System?$skiptoken=A%2FB%3D",
        "https://cm01.contoso.com:443/AdminService/wmi/SMS_R_System?$skiptoken=A%2FB%3D",
    ],
)
def test_absolute_effective_origin_continuations_are_replayed_opaquely(
    link: str,
) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(200, json={"value": [], "@odata.nextLink": link})
        return httpx2.Response(200, json={"value": []})

    client = client_with(httpx2.MockTransport(respond))
    first = client.raw.wmi.query(
        "SMS_R_System", filter="Client eq 1", select=("Name",), top=10
    )
    client.raw.wmi.next_page(first)
    assert len(requests) == 2
    assert requests[1].url.query == b"$skiptoken=A%2FB%3D"
    assert "$filter" not in requests[1].url.params
    assert "$select" not in requests[1].url.params
    assert "$top" not in requests[1].url.params


@pytest.mark.integration
@pytest.mark.parametrize("status", [400, 404])
def test_query_client_statuses_become_safe_query_errors(status: int) -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(status, text="secret response body")
        )
    )
    with pytest.raises(
        QueryError, match=rf"WMI query failed with HTTP {status}"
    ) as caught:
        client.raw.wmi.query("SMS_R_System", filter="Password eq 'secret-filter'")
    message = str(caught.value)
    assert "secret response body" not in message
    assert "secret-filter" not in message
    assert "https://" not in message


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthenticationError), (403, AuthorizationError), (500, ServerError)],
)
def test_query_preserves_stable_executor_status_errors(
    status: int, error: type[Exception]
) -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(status, text="secret response body")
        )
    )
    with pytest.raises(error) as caught:
        client.raw.wmi.query("SMS_R_System", filter="Secret eq 1")
    message = str(caught.value)
    assert "secret response body" not in message
    assert "Secret eq 1" not in message
    assert "https://" not in message


@pytest.mark.integration
def test_wmi_class_name_is_validated_without_request() -> None:
    requests: list[httpx2.Request] = []
    client = client_with(
        httpx2.MockTransport(
            lambda request: (requests.append(request), httpx2.Response(200))[1]
        )
    )
    for entity in ("", " SMS_R_System", "SMS/R_System", "https://evil.example"):
        with pytest.raises(ValueError):
            client.raw.wmi.query(entity)
    assert requests == []


@pytest.mark.integration
@pytest.mark.parametrize(
    ("key", "raw_suffix"),
    [
        (16777219, b"SMS_R_System(16777219)"),
        ("SMS00001", b"SMS_R_System('SMS00001')"),
        ("O'Neil", b"SMS_R_System('O''Neil')"),
        ("slash/value", b"SMS_R_System('slash%2Fvalue')"),
        ("question?value", b"SMS_R_System('question%3Fvalue')"),
        ("hash#value", b"SMS_R_System('hash%23value')"),
        ("percent%value", b"SMS_R_System('percent%25value')"),
        ("space value", b"SMS_R_System('space%20value')"),
        ("Unicode \u96ea", b"SMS_R_System('Unicode%20%E9%9B%AA')"),
        (True, b"SMS_R_System(true)"),
        (False, b"SMS_R_System(false)"),
        (1.5, b"SMS_R_System(1.5)"),
    ],
)
def test_get_serializes_scalar_key_safely_once(
    key: bool | int | float | str, raw_suffix: bytes
) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"Name": "PC001"})

    client = client_with(httpx2.MockTransport(respond))
    result = client.raw.wmi.get(
        "SMS_R_System", key, select=("ResourceId", "Name"), expand=("Resource",)
    )
    assert result == {"Name": "PC001"}
    assert len(requests) == 1
    assert requests[0].url.raw_path.split(b"?")[0] == (
        b"/AdminService/wmi/" + raw_suffix
    )
    assert requests[0].url.fragment == ""
    assert dict(requests[0].url.params) == {
        "$select": "ResourceId,Name",
        "$expand": "Resource",
    }
    assert b"%2525" not in requests[0].url.raw_path


@pytest.mark.integration
@pytest.mark.parametrize("key", [float("nan"), float("inf"), float("-inf")])
def test_get_rejects_non_finite_float_without_request(key: float) -> None:
    requests: list[httpx2.Request] = []
    client = client_with(
        httpx2.MockTransport(
            lambda request: (requests.append(request), httpx2.Response(200))[1]
        )
    )
    with pytest.raises(ValueError, match="finite"):
        client.raw.wmi.get("SMS_R_System", key)
    assert requests == []


@pytest.mark.integration
def test_get_preserves_property_casing() -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200, json={"ResourceId": 123, "Name": "PC001"}
            )
        )
    )
    record = client.raw.wmi.get("SMS_R_System", 123)
    assert record == {"ResourceId": 123, "Name": "PC001"}
    assert record is not None
    assert "ResourceID" not in record


@pytest.mark.integration
@pytest.mark.parametrize("body", [None, [], "bad", 1])
def test_get_rejects_structurally_malformed_responses(body: object) -> None:
    client = client_with(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, json=body))
    )
    with pytest.raises(QueryError, match="malformed"):
        client.raw.wmi.get("SMS_R_System", 123)


@pytest.mark.integration
def test_get_parser_rejects_non_string_mapping_key() -> None:
    with pytest.raises(QueryError, match="malformed"):
        _AdminServiceProviderTransport._parse_entity({1: "bad"})


@pytest.mark.integration
def test_get_rejects_malformed_json() -> None:
    client = client_with(
        httpx2.MockTransport(lambda _request: httpx2.Response(200, content=b"{"))
    )
    with pytest.raises(QueryError, match="malformed"):
        client.raw.wmi.get("SMS_R_System", 123)


@pytest.mark.integration
def test_get_rejects_oversized_response() -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(200, content=b" " * (10 * 1024 * 1024 + 1))
        )
    )
    with pytest.raises(QueryError, match="malformed"):
        client.raw.wmi.get("SMS_R_System", 123)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, QueryError),
        (401, AuthenticationError),
        (403, AuthorizationError),
        (500, ServerError),
    ],
)
def test_get_maps_status_with_safe_error(status: int, error: type[Exception]) -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(status, text="secret response body")
        )
    )
    with pytest.raises(error) as caught:
        client.raw.wmi.get("SMS_R_System", "secret-key")
    message = str(caught.value)
    assert "secret response body" not in message
    assert "secret-key" not in message
    assert "https://" not in message


@pytest.mark.integration
def test_get_404_returns_none_after_exactly_one_request() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(404, text="secret response body")

    client = client_with(httpx2.MockTransport(respond))
    assert client.raw.wmi.get("SMS_R_System", "secret-key") is None
    assert len(requests) == 1


@pytest.mark.integration
def test_get_validates_class_without_request() -> None:
    requests: list[httpx2.Request] = []
    client = client_with(
        httpx2.MockTransport(
            lambda request: (requests.append(request), httpx2.Response(200))[1]
        )
    )
    for entity in ("", " SMS_R_System", "SMS/R_System", "https://evil.example"):
        with pytest.raises(ValueError):
            client.raw.wmi.get(entity, 1)
    assert requests == []
