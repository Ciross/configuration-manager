"""Unit coverage for typed Collection-to-Device members."""

# pyright: reportPrivateUsage=false

from dataclasses import FrozenInstanceError

import pytest

from configuration_manager import (
    CollectionDeviceMember,
    ConfigManager,
    LifecycleError,
    NotFoundError,
    Page,
    QueryError,
)
from configuration_manager.resources.collections import (
    _map_collection_device_member,
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


def member_record(collection_id: str = "SMS00001") -> RawRecord:
    return {
        "CollectionID": collection_id,
        "ResourceID": 16777260,
        "Name": "SBSLPICA01",
        "IgnoredFutureProperty": "future",
    }


class FakeTransport:
    def __init__(self, pages: list[RawPage] | None = None) -> None:
        self.pages = pages or []
        self.requests: list[EntityQuery] = []
        self.key_requests: list[EntityKeyQuery] = []
        self.entity: RawRecord | None = {
            "CollectionID": "SMS00001",
            "CollectionType": 2,
        }

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        return self.pages.pop(0) if self.pages else Page((member_record(),))

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.key_requests.append(request)
        return self.entity

    def query_navigation(self, request: NavigationQuery) -> RawPage | None:
        raise AssertionError("not used")

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        pass


def test_member_mapping_is_strict_frozen_slotted_and_ignores_unknown_fields() -> None:
    member = _map_collection_device_member(member_record(), "SMS00001")
    assert member == CollectionDeviceMember("SMS00001", 16777260, "SBSLPICA01")
    assert _map_collection_device_member(
        {"CollectionID": "JA100014", "ResourceID": 16777260, "Name": None},
        "JA100014",
    ) == CollectionDeviceMember("JA100014", 16777260)
    with pytest.raises(FrozenInstanceError):
        member.device_name = "changed"  # type: ignore[misc]
    assert not hasattr(member, "__dict__")


@pytest.mark.parametrize("value", [None, "", "  ", 1, True])
def test_invalid_collection_id_field(value: object) -> None:
    record: dict[str, JsonValue] = dict(member_record())
    if value is None:
        del record["CollectionID"]
    else:
        record["CollectionID"] = value  # type: ignore[assignment]
    with pytest.raises(QueryError, match="CollectionID"):
        _map_collection_device_member(record, "SMS00001")


def test_mismatched_collection_id_field() -> None:
    with pytest.raises(QueryError, match="does not match"):
        _map_collection_device_member(member_record("OTHER"), "SMS00001")


@pytest.mark.parametrize("value", [None, True, 0, -1, 1.5, "1"])
def test_invalid_resource_id_field(value: object) -> None:
    record: dict[str, JsonValue] = dict(member_record())
    if value is None:
        del record["ResourceID"]
    else:
        record["ResourceID"] = value  # type: ignore[assignment]
    with pytest.raises(QueryError, match="ResourceID"):
        _map_collection_device_member(record, "SMS00001")


def test_missing_and_null_name_map_to_none_but_invalid_name_fails() -> None:
    record: dict[str, JsonValue] = dict(member_record())
    del record["Name"]
    assert _map_collection_device_member(record, "SMS00001").device_name is None
    record["Name"] = None
    assert _map_collection_device_member(record, "SMS00001").device_name is None
    record["Name"] = 1
    with pytest.raises(QueryError, match="Name"):
        _map_collection_device_member(record, "SMS00001")


def test_device_members_validates_root_then_builds_exact_query() -> None:
    transport = FakeTransport()
    page = ConfigManager(transport=transport).collections.device_members(
        "SMS00001", limit=10
    )
    assert page.items == (CollectionDeviceMember("SMS00001", 16777260, "SBSLPICA01"),)
    assert transport.key_requests == [
        EntityKeyQuery(AdminServiceSurface.WMI, "SMS_Collection", "SMS00001")
    ]
    assert transport.requests == [
        EntityQuery(
            AdminServiceSurface.WMI,
            "SMS_FullCollectionMembership",
            options=ODataQueryOptions(
                filter="CollectionID eq 'SMS00001'",
                select=("CollectionID", "ResourceID", "Name"),
                top=10,
            ),
        )
    ]


def test_collection_id_apostrophe_is_escaped_without_changing_identity() -> None:
    transport = FakeTransport([Page((member_record("A'B"),))])
    transport.entity = {"CollectionID": "A'B", "CollectionType": 2}
    ConfigManager(transport=transport).collections.device_members("A'B")
    assert transport.requests[0].options.filter == "CollectionID eq 'A''B'"


@pytest.mark.parametrize("value", [None, "", "  ", 1, True])
def test_invalid_member_ids_make_no_requests(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).collections.device_members(value)  # type: ignore[arg-type]
    assert not transport.key_requests and not transport.requests


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5])
def test_invalid_member_limits_make_no_requests(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).collections.device_members(
            "SMS00001",
            limit=value,  # type: ignore[arg-type]
        )
    assert not transport.key_requests and not transport.requests


@pytest.mark.parametrize("collection_type", [0, 1])
def test_non_device_collection_is_rejected_before_member_query(
    collection_type: int,
) -> None:
    transport = FakeTransport()
    transport.entity = {"CollectionID": "SMS00001", "CollectionType": collection_type}
    with pytest.raises(ValueError, match="device collection"):
        ConfigManager(transport=transport).collections.device_members("SMS00001")
    assert len(transport.key_requests) == 1 and not transport.requests


def test_missing_collection_preserves_not_found_and_empty_device_is_valid() -> None:
    transport = FakeTransport()
    transport.entity = None
    with pytest.raises(NotFoundError, match="not visible"):
        ConfigManager(transport=transport).collections.device_members("SMS00001")
    assert not transport.requests

    empty = FakeTransport([Page(())])
    assert (
        not ConfigManager(transport=empty).collections.device_members("SMS00001").items
    )


def test_member_continuation_binds_owner_and_collection_without_new_lookup() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport((member_record(),), continuation),
            Page((member_record(),)),
        ]
    )
    collections = ConfigManager(transport=transport).collections
    first = collections.device_members("SMS00001")
    second = collections.next_device_members_page(first)
    assert second.items[0].collection_id == "SMS00001"
    assert len(transport.key_requests) == 1
    assert transport.requests[1] == EntityQuery(
        AdminServiceSurface.WMI,
        "SMS_FullCollectionMembership",
        continuation=continuation,
    )


def test_invalid_member_pages_are_rejected_without_requests() -> None:
    continuation = _Continuation(object())
    source_transport = FakeTransport(
        [Page[RawRecord]._from_transport((member_record(),), continuation)]
    )
    source = ConfigManager(transport=source_transport)
    member_page = source.collections.device_members("SMS00001")
    collection_transport = FakeTransport(
        [
            Page[RawRecord]._from_transport(
                ({"CollectionID": "SMS00001", "CollectionType": 2},), continuation
            )
        ]
    )
    collection_page = ConfigManager(transport=collection_transport).collections.list()
    device_transport = FakeTransport(
        [Page[RawRecord]._from_transport(({"MachineId": 1},), continuation)]
    )
    device_page = ConfigManager(transport=device_transport).devices.list()
    target_transport = FakeTransport()
    target = ConfigManager(transport=target_transport).collections
    for page in (member_page, collection_page, device_page):
        with pytest.raises(ValueError, match="originate"):
            target.next_device_members_page(page)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no continuation"):
        target.next_device_members_page(Page((CollectionDeviceMember("x", 1),)))
    assert not target_transport.requests and not target_transport.key_requests


def test_member_iterator_is_lazy_and_continuations_are_incremental() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport((member_record(),), continuation),
            Page((member_record(),)),
        ]
    )
    iterator = ConfigManager(transport=transport).collections.iter_device_members(
        "SMS00001"
    )
    assert not transport.key_requests and not transport.requests
    assert next(iterator).device_id == 16777260
    assert len(transport.key_requests) == 1 and len(transport.requests) == 1
    assert next(iterator).device_id == 16777260
    assert len(transport.key_requests) == 1 and len(transport.requests) == 2


def test_member_operations_respect_lifecycle_including_lazy_iterator() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [Page[RawRecord]._from_transport((member_record(),), continuation)]
    )
    client = ConfigManager(transport=transport)
    collections = client.collections
    page = collections.device_members("SMS00001")
    iterator = collections.iter_device_members("SMS00001")
    client.close()
    with pytest.raises(LifecycleError):
        collections.device_members("SMS00001")
    with pytest.raises(LifecycleError):
        next(iterator)
    with pytest.raises(LifecycleError):
        collections.next_device_members_page(page)
    assert len(transport.requests) == 1 and len(transport.key_requests) == 1
