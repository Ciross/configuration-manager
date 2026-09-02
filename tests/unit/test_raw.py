"""Unit coverage for the public raw provider facade."""

# Internal state is inspected narrowly to verify built-in ownership.
# pyright: reportPrivateUsage=false

import pytest

from configuration_manager import ConfigManager, LifecycleError, Page
from configuration_manager.adminservice_transport import _AdminServiceProviderTransport
from configuration_manager.transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    ProviderMethodCall,
    RawMethodResult,
    RawPage,
    RawRecord,
)


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[EntityQuery] = []
        self.closed = 0

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        return Page(({"Name": "PC"},))

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        raise AssertionError("not used")

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        self.closed += 1


def test_query_builds_typed_wmi_request_and_lifecycle_is_retained() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    wmi = client.raw.wmi
    page = wmi.query("SMS_R_System", filter="Client eq 1", select=("Name",), top=10)
    assert page.items[0]["Name"] == "PC"
    request = transport.requests[0]
    assert request.surface is AdminServiceSurface.WMI
    assert request.entity == "SMS_R_System"
    assert request.options.filter == "Client eq 1"
    assert request.options.select == ("Name",)
    assert request.options.top == 10
    client.close()
    assert transport.closed == 0
    with pytest.raises(LifecycleError):
        wmi.query("SMS_R_System")


def test_owned_injected_transport_closes_once() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport, own_transport=True)
    client.close()
    client.close()
    assert transport.closed == 1


def test_iterator_is_lazy() -> None:
    transport = FakeTransport()
    iterator = ConfigManager(transport=transport).raw.wmi.iter("SMS_R_System")
    assert transport.requests == []
    assert next(iterator)["Name"] == "PC"
    assert len(transport.requests) == 1


def test_builtin_transport_is_locally_constructed_owned_and_closed() -> None:
    client = ConfigManager(server="does-not-resolve.invalid")
    wmi = client.raw.wmi
    transport = client._transport
    assert isinstance(transport, _AdminServiceProviderTransport)
    assert client._own_transport is True
    assert not transport._admin.closed

    client.close()
    client.close()
    assert transport._admin.closed
    with pytest.raises(LifecycleError):
        wmi.query("SMS_R_System")


def test_builtin_context_closes_internal_stack() -> None:
    with ConfigManager(server="does-not-resolve.invalid") as client:
        transport = client._transport
        assert isinstance(transport, _AdminServiceProviderTransport)
        assert not transport._admin.closed
    assert transport._admin.closed
