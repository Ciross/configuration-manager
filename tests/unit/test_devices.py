"""Unit coverage for Device mapping and resource operations."""

# Private values are used to construct controlled provider continuations.
# pyright: reportPrivateUsage=false

from dataclasses import FrozenInstanceError
from datetime import UTC, timedelta

import pytest

from configuration_manager import (
    ConfigManager,
    Device,
    DeviceCollectionMembership,
    LifecycleError,
    NotFoundError,
    Page,
    QueryError,
)
from configuration_manager.resources.devices import (
    _DeviceCollectionMembershipsContinuation,
    _map_device,
    _map_device_collection_membership,
)
from configuration_manager.transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonValue,
    NavigationQuery,
    ODataQueryOptions,
    ProviderMethodCall,
    RawMethodResult,
    RawPage,
    RawRecord,
    _Continuation,
)


class FakeTransport:
    def __init__(self, pages: list[RawPage] | None = None) -> None:
        self.pages = pages or []
        self.requests: list[EntityQuery] = []
        self.key_requests: list[EntityKeyQuery] = []
        self.entity: RawRecord | None = {"MachineId": 123, "Name": "PC001"}
        self.navigation_pages: list[RawPage | None] = []
        self.navigation_requests: list[NavigationQuery] = []

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        if self.pages:
            return self.pages.pop(0)
        return Page(({"MachineId": 123, "Name": "PC001"},))

    def query_navigation(self, request: NavigationQuery) -> RawPage | None:
        self.navigation_requests.append(request)
        if self.navigation_pages:
            return self.navigation_pages.pop(0)
        return Page(({"Collection": {"SiteID": "SMS00001"}},))

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.key_requests.append(request)
        return self.entity

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        pass


def test_complete_payload_maps_to_frozen_device_and_ignores_unknown_fields() -> None:
    device = _map_device(
        {
            "MachineId": 123,
            "Name": "PC001",
            "ClientVersion": "5.00.9128.1000",
            "DeviceOS": "Microsoft Windows NT Workstation 10.0",
            "IsActive": True,
            "LastActiveTime": "2026-09-03T06:12:30Z",
            "UnknownFutureProperty": "ignored",
        }
    )
    assert device == Device(
        123,
        "PC001",
        "5.00.9128.1000",
        "Microsoft Windows NT Workstation 10.0",
        True,
        device.last_active_time,
    )
    assert device.last_active_time is not None
    assert device.last_active_time.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        device.name = "changed"  # type: ignore[misc]
    assert not hasattr(device, "__dict__")


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"MachineId": None},
        {"MachineId": True},
        {"MachineId": "1"},
        {"MachineId": 1.0},
    ],
)
def test_invalid_or_missing_machine_id_is_rejected(record: RawRecord) -> None:
    with pytest.raises(QueryError, match="MachineId"):
        _map_device(record)


def test_missing_and_null_optional_fields_map_to_none() -> None:
    assert _map_device({"MachineId": 1}) == Device(1)
    assert _map_device(
        {"MachineId": 1, "Name": None, "IsActive": None, "LastActiveTime": None}
    ) == Device(1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (True, True),
        (False, False),
        (1, True),
        (0, False),
    ],
)
def test_boolean_like_is_active_values_are_normalized(
    raw: JsonValue, expected: bool | None
) -> None:
    device = _map_device({"MachineId": 1, "IsActive": raw})
    assert device.is_active is expected
    assert device.is_active is None or type(device.is_active) is bool


@pytest.mark.parametrize(
    "raw", [-1, 2, 100, 0.0, 1.0, "0", "1", "true", "false", [], {}]
)
def test_invalid_is_active_values_are_rejected(raw: JsonValue) -> None:
    with pytest.raises(QueryError, match="IsActive"):
        _map_device({"MachineId": 1, "IsActive": raw})


@pytest.mark.parametrize(
    "record",
    [
        {"MachineId": 1, "Name": 2},
        {"MachineId": 1, "ClientVersion": False},
        {"MachineId": 1, "DeviceOS": []},
    ],
)
def test_malformed_known_optional_fields_are_rejected(record: RawRecord) -> None:
    with pytest.raises(QueryError):
        _map_device(record)


def test_offset_timestamp_is_aware() -> None:
    value = _map_device(
        {"MachineId": 1, "LastActiveTime": "2026-09-03T06:12:30-05:30"}
    ).last_active_time
    assert value is not None
    assert value.utcoffset() == -timedelta(hours=5, minutes=30)


@pytest.mark.parametrize("value", ["not-a-time", "2026-09-03T06:12:30"])
def test_invalid_or_naive_timestamp_is_rejected(value: str) -> None:
    with pytest.raises(QueryError):
        _map_device({"MachineId": 1, "LastActiveTime": value})


def test_list_builds_one_v1_query_and_wraps_continuation() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [Page[RawRecord]._from_transport(({"MachineId": 1},), continuation)]
    )
    client = ConfigManager(transport=transport)
    page = client.devices.list(limit=10)
    assert page.items == (Device(1),)
    assert page.has_next
    assert transport.requests == [
        EntityQuery(
            AdminServiceSurface.V1,
            "Device",
            options=transport.requests[0].options,
        )
    ]
    assert transport.requests[0].options.top == 10


def test_get_builds_one_key_query_maps_and_does_not_cache() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    assert client.devices.get(123) == Device(123, "PC001")
    assert client.devices.get(123) == Device(123, "PC001")
    assert transport.key_requests == [
        EntityKeyQuery(AdminServiceSurface.V1, "Device", 123),
        EntityKeyQuery(AdminServiceSurface.V1, "Device", 123),
    ]
    assert transport.requests == []


def test_get_none_is_not_found_without_disclosing_id() -> None:
    transport = FakeTransport()
    transport.entity = None
    with pytest.raises(NotFoundError, match="not visible") as caught:
        ConfigManager(transport=transport).devices.get(123)
    assert "123" not in str(caught.value)


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5])
def test_invalid_ids_are_rejected_without_request(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).devices.get(value)  # type: ignore[arg-type]
    assert transport.key_requests == []


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5])
def test_invalid_limits_are_rejected_without_request(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).devices.list(limit=value)  # type: ignore[arg-type]
    assert transport.requests == []


def test_next_page_passes_continuation_and_maps_typed_result() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport(({"MachineId": 1},), continuation),
            Page(({"MachineId": 2},)),
        ]
    )
    devices = ConfigManager(transport=transport).devices
    second = devices.next_page(devices.list())
    assert second.items == (Device(2),)
    assert transport.requests[1] == EntityQuery(
        AdminServiceSurface.V1, "Device", continuation=continuation
    )


def test_invalid_page_origins_are_rejected_without_request() -> None:
    continuation = _Continuation(object())
    first_transport = FakeTransport(
        [Page[RawRecord]._from_transport(({"MachineId": 1},), continuation)]
    )
    page = ConfigManager(transport=first_transport).devices.list()
    other_transport = FakeTransport()
    other = ConfigManager(transport=other_transport)
    with pytest.raises(ValueError, match="originate"):
        other.devices.next_page(page)
    raw_page = Page[RawRecord]._from_transport(({"MachineId": 1},), continuation)
    with pytest.raises(ValueError, match="originate"):
        other.devices.next_page(raw_page)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no continuation"):
        other.devices.next_page(Page((Device(1),)))
    assert other_transport.requests == []


def test_iterator_is_lazy_and_traverses_pages_incrementally() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport(({"MachineId": 1},), continuation),
            Page(({"MachineId": 2},)),
        ]
    )
    iterator = ConfigManager(transport=transport).devices.iter()
    assert transport.requests == []
    assert next(iterator) == Device(1)
    assert len(transport.requests) == 1
    assert next(iterator) == Device(2)
    assert len(transport.requests) == 2


def test_retained_manager_respects_client_lifecycle() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    devices = client.devices
    client.close()
    with pytest.raises(LifecycleError):
        devices.list()
    with pytest.raises(LifecycleError):
        devices.get(123)
    with pytest.raises(LifecycleError):
        next(devices.iter())
    assert transport.requests == []
    assert transport.key_requests == []


def test_membership_mapper_is_strict_frozen_and_ignores_unknown_fields() -> None:
    membership = _map_device_collection_membership(
        {
            "Collection": {
                "SiteID": "JA100014",
                "CollectionID": 16777229,
                "CollectionName": "All Servers",
                "Flags": 4,
                "IgnoredFutureProperty": "future",
            },
            "IgnoredMembershipProperty": 123,
        },
        16777260,
    )
    assert membership == DeviceCollectionMembership(16777260, "JA100014", "All Servers")
    with pytest.raises(FrozenInstanceError):
        membership.collection_id = "changed"  # type: ignore[misc]
    assert not hasattr(membership, "__dict__")


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"Collection": None},
        {"Collection": []},
        {"Collection": "bad"},
        {"Collection": {}},
        {"Collection": {"SiteID": None}},
        {"Collection": {"SiteID": ""}},
        {"Collection": {"SiteID": "   "}},
        {"Collection": {"SiteID": 1}},
        {"Collection": {"SiteID": True}},
        {"Collection": {"SiteID": 1.5}},
        {"Collection": {"SiteID": []}},
        {"Collection": {"SiteID": {}}},
        {"Collection": {"SiteID": "SMS00001", "CollectionName": 1}},
    ],
)
def test_invalid_membership_payload_is_rejected(record: RawRecord) -> None:
    with pytest.raises(QueryError):
        _map_device_collection_membership(record, 1)


def test_collection_memberships_builds_exact_navigation_query() -> None:
    transport = FakeTransport()
    page = ConfigManager(transport=transport).devices.collection_memberships(
        16777260, limit=10
    )
    assert page.items == (DeviceCollectionMembership(16777260, "SMS00001"),)
    assert transport.navigation_requests == [
        NavigationQuery(
            AdminServiceSurface.V1,
            "Device",
            16777260,
            "ResourceCollectionMembership",
            ODataQueryOptions(select=("Collection",), expand=("Collection",), top=10),
        )
    ]


def test_membership_mapper_accepts_null_live_collection_name() -> None:
    assert _map_device_collection_membership(
        {
            "Collection": {
                "SiteID": "SMS00001",
                "CollectionName": None,
                "CollectionID": 123,
            }
        },
        16777260,
    ) == DeviceCollectionMembership(16777260, "SMS00001")


def test_membership_mapper_rejects_old_guessed_field_names() -> None:
    with pytest.raises(QueryError, match="SiteID"):
        _map_device_collection_membership(
            {
                "Collection": {
                    "CollectionID": "SMS00001",
                    "Name": "All Systems",
                }
            },
            16777260,
        )


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5])
def test_invalid_membership_ids_are_rejected_without_request(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).devices.collection_memberships(  # type: ignore[arg-type]
            value  # type: ignore[arg-type]
        )
    assert transport.navigation_requests == []


def test_membership_not_found_and_invalid_limit_do_not_leak_or_extra_query() -> None:
    transport = FakeTransport()
    transport.navigation_pages = [None]
    with pytest.raises(NotFoundError, match="not visible"):
        ConfigManager(transport=transport).devices.collection_memberships(123)
    assert len(transport.navigation_requests) == 1
    other = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=other).devices.collection_memberships(123, limit=True)
    assert other.navigation_requests == []


def test_membership_continuation_retains_device_and_rejects_other_pages() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport()
    transport.navigation_pages = [
        Page[RawRecord]._from_transport(
            ({"Collection": {"SiteID": "A"}},), continuation
        ),
        Page(({"Collection": {"SiteID": "B", "CollectionName": "Second"}},)),
    ]
    devices = ConfigManager(transport=transport).devices
    first = devices.collection_memberships(42)
    second = devices.next_collection_memberships_page(first)
    assert second.items == (DeviceCollectionMembership(42, "B", "Second"),)
    assert transport.navigation_requests[1].key == 42
    assert transport.navigation_requests[1].continuation is continuation

    other_transport = FakeTransport()
    other = ConfigManager(transport=other_transport).devices
    with pytest.raises(ValueError, match="originate"):
        other.next_collection_memberships_page(first)
    with pytest.raises(ValueError, match="no continuation"):
        devices.next_collection_memberships_page(Page(second.items))
    assert other_transport.navigation_requests == []


def test_membership_iterator_is_lazy_and_closed_operations_do_no_io() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport()
    transport.navigation_pages = [
        Page[RawRecord]._from_transport(
            ({"Collection": {"SiteID": "A"}},), continuation
        ),
        Page(({"Collection": {"SiteID": "B"}},)),
    ]
    client = ConfigManager(transport=transport)
    iterator = client.devices.iter_collection_memberships(99)
    assert transport.navigation_requests == []
    assert next(iterator) == DeviceCollectionMembership(99, "A")
    assert len(transport.navigation_requests) == 1
    assert next(iterator) == DeviceCollectionMembership(99, "B")
    assert len(transport.navigation_requests) == 2
    retained = client.devices
    client.close()
    with pytest.raises(LifecycleError):
        retained.collection_memberships(99)
    with pytest.raises(LifecycleError):
        retained.next_collection_memberships_page(
            Page[DeviceCollectionMembership]._from_transport(
                (),
                _DeviceCollectionMembershipsContinuation(
                    retained, 99, _Continuation(object())
                ),
            )
        )
    assert len(transport.navigation_requests) == 2
