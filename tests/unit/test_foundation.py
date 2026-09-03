"""Tests for the executable SDK foundation."""

# Private usage is intentional where tests exercise transport-only construction seams.
# pyright: reportPrivateUsage=false

import importlib
import inspect
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

import configuration_manager
from configuration_manager import (
    ConfigManager,
    ConfigurationError,
    ConfigurationManagerError,
    LifecycleError,
    Page,
    TransportConnectionError,
    TransportError,
    TransportTimeoutError,
)
from configuration_manager.config import ConfigManagerConfig
from configuration_manager.transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonValue,
    MethodTarget,
    ODataQueryOptions,
    ProviderMethodCall,
    ProviderTransport,
    RawMethodResult,
    RawPage,
    RawRecord,
    _Continuation,
)


class FakeTransport:
    """Typed, inert structural implementation of the capability protocol."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.calls.append("query")
        return Page(())

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.calls.append("get")
        return None

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        self.calls.append("invoke")
        return None

    def close(self) -> None:
        self.calls.append("close")


def accepts_transport(transport: ProviderTransport) -> ProviderTransport:
    """Provide a static structural-typing assertion for Pyright."""
    return transport


def test_exception_hierarchy_and_root_catch() -> None:
    """Transport errors inherit through both documented base classes."""
    assert issubclass(TransportConnectionError, TransportError)
    assert issubclass(TransportTimeoutError, TransportError)
    with pytest.raises(ConfigurationManagerError):
        raise TransportConnectionError("failed")


@pytest.mark.parametrize(
    "server",
    [
        "https://cm01.contoso.com",
        "http://cm01.contoso.com",
        "cm01.contoso.com/AdminService",
        "user:password@cm01.contoso.com",
        "cm01.contoso.com:8443",
        "cm01.contoso.com?x=1",
        "cm01.contoso.com#fragment",
    ],
)
def test_invalid_server_forms_are_rejected(server: str) -> None:
    """The simple server input never accepts URL components."""
    with pytest.raises(ConfigurationError):
        ConfigManager(server=server)


def test_config_is_immutable_normalized_and_tls_verified_by_default() -> None:
    """Local configuration normalizes DNS casing and remains immutable."""
    config = ConfigManagerConfig("CM01.Contoso.COM")
    assert config.server == "cm01.contoso.com"
    assert config.verify_tls is True
    with pytest.raises(FrozenInstanceError):
        config.server = "other.example.com"  # type: ignore[misc]


def test_configuration_modes_are_exclusive() -> None:
    """Injected transports cannot be combined with built-in settings."""
    transport = FakeTransport()
    with pytest.raises(ConfigurationError):
        ConfigManager(server="cm01", transport=transport)
    with pytest.raises(ConfigurationError):
        ConfigManager(transport=transport, verify_tls=False)
    with pytest.raises(ConfigurationError):
        ConfigManager(server="cm01", own_transport=True)
    with pytest.raises(ConfigurationError):
        ConfigManager()


def test_page_materializes_items_and_hides_opaque_continuation() -> None:
    """A page is an immutable, passive snapshot of exactly one page."""
    source = [1, 2]
    page: Page[int] = Page(source)
    source.append(3)
    assert page.items == (1, 2)
    assert not page.has_next
    continued = Page[int]._from_transport((1,), _Continuation(object()))
    assert continued.has_next
    assert "Continuation" not in repr(continued)
    assert tuple(inspect.signature(Page).parameters) == ("items",)
    assert not hasattr(page, "next")
    with pytest.raises(FrozenInstanceError):
        page.items = ()  # type: ignore[misc]


def test_odata_options_are_immutable_and_structurally_validated() -> None:
    """OData $top is represented as a positive result limit."""
    options = ODataQueryOptions(select=("Name",), top=10)
    assert options.select == ("Name",)
    assert options.top == 10
    with pytest.raises(FrozenInstanceError):
        options.top = 11  # type: ignore[misc]
    with pytest.raises(ValueError, match="positive"):
        ODataQueryOptions(top=0)
    with pytest.raises(ValueError, match="property names"):
        ODataQueryOptions(order_by=("",))


def test_capability_values_and_transport_are_strongly_typed() -> None:
    """Capability values express provider concepts without executing work."""
    transport = FakeTransport()
    assert accepts_transport(transport) is transport
    value: JsonValue = {"Name": "PC001", "Flags": [1, True, None]}
    query = EntityQuery(
        AdminServiceSurface.WMI,
        "SMS_R_System",
        ODataQueryOptions(filter="Client eq true"),
    )
    key_query = EntityKeyQuery(AdminServiceSurface.V1, "Device", 1)
    call = ProviderMethodCall(
        AdminServiceSurface.WMI,
        "SMS_Admin",
        "Example",
        MethodTarget.STATIC,
        parameters={"input": value},
    )
    assert query.surface is AdminServiceSurface.WMI
    assert key_query.key == 1
    assert call.parameters["input"] == value
    assert transport.calls == []


def test_entity_key_must_not_be_null() -> None:
    """Entity lookup requests reject a null key at runtime boundaries."""
    with pytest.raises(ValueError, match="must not be None"):
        EntityKeyQuery(
            AdminServiceSurface.V1,
            "Device",
            cast("bool | int | float | str", None),
        )


@pytest.mark.parametrize(
    ("target", "key", "message"),
    [
        (MethodTarget.STATIC, 1, "must not have"),
        (MethodTarget.INSTANCE, None, "requires"),
    ],
)
def test_method_target_and_key_must_agree(
    target: MethodTarget, key: bool | int | float | str | None, message: str
) -> None:
    """Provider method requests cannot represent impossible target/key pairs."""
    with pytest.raises(ValueError, match=message):
        ProviderMethodCall(
            AdminServiceSurface.WMI,
            "SMS_R_System",
            "Example",
            target,
            key=key,
        )


@pytest.mark.parametrize(("entity", "method"), [("", "Example"), ("Device", " ")])
def test_method_names_must_not_be_empty(entity: str, method: str) -> None:
    """Provider method requests reject obviously empty names."""
    with pytest.raises(ValueError, match="must not be empty"):
        ProviderMethodCall(AdminServiceSurface.V1, entity, method, MethodTarget.STATIC)


def test_auth_placeholder_module_is_removed() -> None:
    """No meaningless executable authentication marker is published."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("configuration_manager.auth")


def test_client_lifecycle_and_external_transport_ownership() -> None:
    """Construction is inert and external transports remain caller-owned."""
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    assert transport.calls == []
    assert client.config is None
    assert client.__enter__() is client
    client.close()
    client.close()
    assert client.closed
    assert transport.calls == []
    with pytest.raises(LifecycleError):
        _ = client.config
    with pytest.raises(LifecycleError):
        client.__enter__()


def test_context_manager_closes_owned_transport_once() -> None:
    """Explicitly transferred transport ownership is honored by contexts."""
    transport = FakeTransport()
    with ConfigManager(transport=transport, own_transport=True) as client:
        assert not client.closed
    client.close()
    assert transport.calls == ["close"]


def test_public_exports_are_curated() -> None:
    """The package root exposes only the intended initial public API."""
    expected = {
        "AmbiguousResultError",
        "AuthenticationError",
        "AuthorizationError",
        "Collection",
        "CollectionType",
        "ConfigManager",
        "ConfigurationError",
        "ConfigurationManagerError",
        "Device",
        "LifecycleError",
        "MethodInvocationError",
        "NotFoundError",
        "Page",
        "QueryError",
        "ServerError",
        "TLSVerificationError",
        "TransportConnectionError",
        "TransportError",
        "TransportTimeoutError",
    }
    assert set(configuration_manager.__all__) == expected
    assert cast(object, configuration_manager.ConfigManager) is ConfigManager
