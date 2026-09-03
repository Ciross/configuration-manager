"""Controlled HTTP coverage for the high-level Collection boundary."""

# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import (
    Collection,
    CollectionType,
    ConfigManager,
    NotFoundError,
    QueryError,
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


def record() -> dict[str, object]:
    return {
        "CollectionID": "SMS00001",
        "Name": "All Systems",
        "CollectionType": 2,
        "MemberCount": 123,
        "LimitToCollectionID": None,
        "LimitToCollectionName": None,
        "IsBuiltIn": True,
        "IgnoredFutureProperty": "future",
    }


@pytest.mark.integration
def test_typed_list_uses_wmi_route_and_top() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"value": [record()]})

    with client_with(httpx2.MockTransport(respond)) as client:
        page = client.collections.list(limit=1)
    assert page.items == (
        Collection(
            "SMS00001", "All Systems", CollectionType.DEVICE, 123, None, None, True
        ),
    )
    assert requests[0].url.path == "/AdminService/wmi/SMS_Collection"
    assert dict(requests[0].url.params) == {"$top": "1"}


@pytest.mark.integration
def test_typed_get_uses_keyed_wmi_route() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=record())

    with client_with(httpx2.MockTransport(respond)) as client:
        collection = client.collections.get("SMS00001")
    assert isinstance(collection, Collection)
    assert requests[0].url.path == "/AdminService/wmi/SMS_Collection('SMS00001')"


@pytest.mark.integration
def test_keyed_404_becomes_high_level_not_found() -> None:
    client = client_with(httpx2.MockTransport(lambda _request: httpx2.Response(404)))
    with pytest.raises(NotFoundError, match="not visible"):
        client.collections.get("SMS00001")


@pytest.mark.integration
@pytest.mark.parametrize(
    "invalid", [{"CollectionID": None}, {"CollectionType": 3}, {"MemberCount": -1}]
)
def test_malformed_known_field_becomes_query_error(invalid: dict[str, object]) -> None:
    payload = record()
    payload.update(invalid)
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={"value": [payload]})
        )
    )
    with pytest.raises(QueryError):
        client.collections.list()
