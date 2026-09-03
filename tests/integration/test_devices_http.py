"""Controlled HTTP coverage for the high-level Device boundary."""

# The concrete internal provider is intentionally exercised at this boundary.
# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import ConfigManager, Device, NotFoundError, QueryError
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
def test_typed_list_uses_v1_route_and_top() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "value": [
                    {
                        "MachineId": 123,
                        "Name": "PC001",
                        "ClientVersion": "5.00.9128.1000",
                        "DeviceOS": "Microsoft Windows NT Workstation 10.0",
                        "IsActive": 1,
                        "LastActiveTime": "2026-09-03T06:12:30Z",
                        "IgnoredNewField": "future",
                    }
                ]
            },
        )

    with client_with(httpx2.MockTransport(respond)) as client:
        page = client.devices.list(limit=1)
    assert page.items[0] == Device(
        123,
        "PC001",
        "5.00.9128.1000",
        "Microsoft Windows NT Workstation 10.0",
        True,
        page.items[0].last_active_time,
    )
    assert page.items[0].is_active is True
    assert requests[0].url.path == "/AdminService/v1.0/Device"
    assert dict(requests[0].url.params) == {"$top": "1"}


@pytest.mark.integration
def test_typed_get_uses_keyed_v1_route() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200, json={"MachineId": 123, "Name": "PC001", "IsActive": 0}
        )

    with client_with(httpx2.MockTransport(respond)) as client:
        device = client.devices.get(123)
    assert device == Device(123, "PC001", is_active=False)
    assert device.is_active is False
    assert requests[0].url.path == "/AdminService/v1.0/Device(123)"


@pytest.mark.integration
def test_typed_device_accepts_json_boolean_is_active() -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200, json={"MachineId": 125, "IsActive": True}
            )
        )
    )
    assert client.devices.get(125).is_active is True


@pytest.mark.integration
def test_raw_v1_preserves_numeric_is_active() -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200, json={"MachineId": 123, "IsActive": 1}
            )
        )
    )
    record = client.raw.v1.get("Device", 123)
    assert record is not None
    assert record["IsActive"] == 1
    assert type(record["IsActive"]) is int


@pytest.mark.integration
def test_keyed_404_becomes_high_level_not_found() -> None:
    client = client_with(httpx2.MockTransport(lambda _request: httpx2.Response(404)))
    with pytest.raises(NotFoundError, match="not visible"):
        client.devices.get(123)


@pytest.mark.integration
@pytest.mark.parametrize(
    "record", [{"MachineId": "123"}, {"MachineId": 123, "IsActive": 2}]
)
def test_malformed_known_field_becomes_query_error(record: object) -> None:
    client = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(200, json={"value": [record]})
        )
    )
    with pytest.raises(QueryError):
        client.devices.list()
