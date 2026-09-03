"""Controlled HTTP coverage for the high-level Collection boundary."""

# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import (
    Collection,
    CollectionDeviceMember,
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


@pytest.mark.integration
def test_device_members_use_keyed_validation_then_filtered_wmi_query() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(200, json=record())
        return httpx2.Response(
            200,
            json={
                "value": [
                    {
                        "CollectionID": "SMS00001",
                        "ResourceID": 16777260,
                        "Name": "SBSLPICA01",
                        "IgnoredFutureProperty": "future",
                    }
                ]
            },
        )

    with client_with(httpx2.MockTransport(respond)) as client:
        page = client.collections.device_members("SMS00001", limit=1)
    assert page.items == (CollectionDeviceMember("SMS00001", 16777260, "SBSLPICA01"),)
    assert requests[0].url.path == "/AdminService/wmi/SMS_Collection('SMS00001')"
    assert requests[1].url.path == "/AdminService/wmi/SMS_FullCollectionMembership"
    assert dict(requests[1].url.params) == {
        "$filter": "CollectionID eq 'SMS00001'",
        "$select": "CollectionID,ResourceID,Name",
        "$top": "1",
    }


@pytest.mark.integration
@pytest.mark.parametrize("status_or_type", [404, 1])
def test_invalid_collection_stops_before_membership_get(status_or_type: int) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if status_or_type == 404:
            return httpx2.Response(404)
        payload = record()
        payload["CollectionType"] = status_or_type
        return httpx2.Response(200, json=payload)

    client = client_with(httpx2.MockTransport(respond))
    expected = NotFoundError if status_or_type == 404 else ValueError
    with pytest.raises(expected):
        client.collections.device_members("SMS00001")
    assert len(requests) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    ("membership", "expected"),
    [([], None), ([{"CollectionID": "SMS00001", "ResourceID": 0}], QueryError)],
)
def test_empty_and_malformed_device_memberships(
    membership: list[dict[str, object]], expected: type[Exception] | None
) -> None:
    calls = 0

    def respond(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            200, json=record() if calls == 1 else {"value": membership}
        )

    client = client_with(httpx2.MockTransport(respond))
    if expected is None:
        assert client.collections.device_members("SMS00001").items == ()
    else:
        with pytest.raises(expected):
            client.collections.device_members("SMS00001")


@pytest.mark.integration
def test_device_member_continuation_replays_server_url_without_collection_lookup() -> (
    None
):
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(200, json=record())
        if len(requests) == 2:
            return httpx2.Response(
                200,
                json={
                    "value": [member],
                    "@odata.nextLink": (
                        "https://cm01.contoso.com/AdminService/wmi/"
                        "SMS_FullCollectionMembership?$skiptoken=opaque%2Bvalue"
                    ),
                },
            )
        return httpx2.Response(200, json={"value": [member]})

    member = {"CollectionID": "SMS00001", "ResourceID": 16777260, "Name": None}
    with client_with(httpx2.MockTransport(respond)) as client:
        first = client.collections.device_members("SMS00001")
        second = client.collections.next_device_members_page(first)
    assert second.items == (CollectionDeviceMember("SMS00001", 16777260),)
    assert len(requests) == 3
    assert requests[2].url.path == "/AdminService/wmi/SMS_FullCollectionMembership"
    assert requests[2].url.query == b"$skiptoken=opaque%2Bvalue"
