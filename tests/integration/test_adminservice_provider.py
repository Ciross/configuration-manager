"""Controlled HTTP coverage for AdminService WMI collection queries."""

# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import ConfigManager, QueryError
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
