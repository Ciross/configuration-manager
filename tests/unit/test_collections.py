"""Unit coverage for Collection mapping and resource operations."""

# pyright: reportPrivateUsage=false

from dataclasses import FrozenInstanceError

import pytest

from configuration_manager import (
    Collection,
    CollectionType,
    ConfigManager,
    LifecycleError,
    NotFoundError,
    Page,
    QueryError,
)
from configuration_manager.resources.collections import _map_collection
from configuration_manager.transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonValue,
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
        self.entity: RawRecord | None = collection_record()

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        return self.pages.pop(0) if self.pages else Page((collection_record(),))

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.key_requests.append(request)
        return self.entity

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        pass


def collection_record(id: str = "SMS00001") -> RawRecord:
    return {"CollectionID": id, "Name": "All Systems", "CollectionType": 2}


def test_complete_payload_maps_to_frozen_collection_and_ignores_unknown_fields() -> (
    None
):
    collection = _map_collection(
        {
            "CollectionID": "SMS00001",
            "Name": "All Systems",
            "CollectionType": 2,
            "MemberCount": 123,
            "LimitToCollectionID": None,
            "LimitToCollectionName": None,
            "IsBuiltIn": True,
            "SomeFutureProperty": "ignored",
        }
    )
    assert collection == Collection(
        "SMS00001", "All Systems", CollectionType.DEVICE, 123, None, None, True
    )
    with pytest.raises(FrozenInstanceError):
        collection.name = "changed"  # type: ignore[misc]
    assert not hasattr(collection, "__dict__")


@pytest.mark.parametrize("value", [None, "", "   ", 1, True, [], {}])
def test_invalid_or_missing_collection_id_is_rejected(value: JsonValue) -> None:
    record: dict[str, JsonValue] = {"CollectionType": 2}
    if value is not None:
        record["CollectionID"] = value
    with pytest.raises(QueryError, match="CollectionID"):
        _map_collection(record)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, CollectionType.OTHER), (1, CollectionType.USER), (2, CollectionType.DEVICE)],
)
def test_collection_types(value: int, expected: CollectionType) -> None:
    assert (
        _map_collection({"CollectionID": "x", "CollectionType": value}).collection_type
        is expected
    )


@pytest.mark.parametrize("value", [None, True, 3, -1, 1.0, "1"])
def test_invalid_or_missing_collection_type_is_rejected(value: JsonValue) -> None:
    record: dict[str, JsonValue] = {"CollectionID": "x"}
    if value is not None:
        record["CollectionType"] = value
    with pytest.raises(QueryError, match="CollectionType"):
        _map_collection(record)


def test_missing_and_nullable_optional_fields_map_to_none() -> None:
    expected = Collection("x", None, CollectionType.OTHER)
    assert _map_collection({"CollectionID": "x", "CollectionType": 0}) == expected
    assert (
        _map_collection(
            {
                "CollectionID": "x",
                "CollectionType": 0,
                "Name": None,
                "MemberCount": None,
                "LimitToCollectionID": None,
                "LimitToCollectionName": None,
                "IsBuiltIn": None,
            }
        )
        == expected
    )


@pytest.mark.parametrize(
    "field", ["Name", "LimitToCollectionID", "LimitToCollectionName"]
)
def test_invalid_optional_strings(field: str) -> None:
    with pytest.raises(QueryError, match=field):
        _map_collection({"CollectionID": "x", "CollectionType": 0, field: 1})


@pytest.mark.parametrize("value", [-1, True, 1.0, "1"])
def test_invalid_member_count(value: JsonValue) -> None:
    with pytest.raises(QueryError, match="MemberCount"):
        _map_collection(
            {"CollectionID": "x", "CollectionType": 0, "MemberCount": value}
        )


def test_valid_member_count_and_is_builtin() -> None:
    result = _map_collection(
        {"CollectionID": "x", "CollectionType": 1, "MemberCount": 0, "IsBuiltIn": False}
    )
    assert result.member_count == 0
    assert result.is_builtin is False


@pytest.mark.parametrize("value", [0, 1, "true", []])
def test_invalid_is_builtin(value: JsonValue) -> None:
    with pytest.raises(QueryError, match="IsBuiltIn"):
        _map_collection({"CollectionID": "x", "CollectionType": 0, "IsBuiltIn": value})


def test_list_builds_one_wmi_query_and_wraps_continuation() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [Page[RawRecord]._from_transport((collection_record(),), continuation)]
    )
    page = ConfigManager(transport=transport).collections.list(limit=10)
    assert isinstance(page.items[0], Collection)
    assert page.has_next
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.surface is AdminServiceSurface.WMI
    assert request.entity == "SMS_Collection"
    assert request.options.top == 10


def test_get_builds_key_query_maps_does_not_cache_and_none_is_not_found() -> None:
    transport = FakeTransport()
    collections = ConfigManager(transport=transport).collections
    assert collections.get("SMS00001").id == "SMS00001"
    assert collections.get("SMS00001").id == "SMS00001"
    assert (
        transport.key_requests
        == [EntityKeyQuery(AdminServiceSurface.WMI, "SMS_Collection", "SMS00001")] * 2
    )
    transport.entity = None
    with pytest.raises(NotFoundError, match="not visible") as caught:
        collections.get("Secret")
    assert "Secret" not in str(caught.value)


@pytest.mark.parametrize("value", [None, "", "   ", 1, True, []])
def test_invalid_ids_are_rejected_without_request(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).collections.get(value)  # type: ignore[arg-type]
    assert transport.key_requests == []


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5])
def test_invalid_limits_are_rejected_without_request(value: object) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        ConfigManager(transport=transport).collections.list(limit=value)  # type: ignore[arg-type]
    assert transport.requests == []


def test_next_page_passes_continuation_and_maps_typed_result() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport((collection_record(),), continuation),
            Page((collection_record("P0100042"),)),
        ]
    )
    collections = ConfigManager(transport=transport).collections
    second = collections.next_page(collections.list())
    assert second.items[0].id == "P0100042"
    assert transport.requests[1] == EntityQuery(
        AdminServiceSurface.WMI, "SMS_Collection", continuation=continuation
    )


def test_invalid_page_origins_are_rejected_without_request() -> None:
    continuation = _Continuation(object())
    source = ConfigManager(
        transport=FakeTransport(
            [Page[RawRecord]._from_transport((collection_record(),), continuation)]
        )
    )
    collection_page = source.collections.list()
    device_transport = FakeTransport(
        [Page[RawRecord]._from_transport(({"MachineId": 1},), continuation)]
    )
    device_page = ConfigManager(transport=device_transport).devices.list()
    raw_transport = FakeTransport(
        [Page[RawRecord]._from_transport((collection_record(),), continuation)]
    )
    raw_page = ConfigManager(transport=raw_transport).raw.wmi.query("SMS_Collection")
    target_transport = FakeTransport()
    target = ConfigManager(transport=target_transport).collections
    for page in (collection_page, device_page, raw_page):
        with pytest.raises(ValueError, match="originate"):
            target.next_page(page)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no continuation"):
        target.next_page(Page((Collection("x", None, CollectionType.OTHER),)))
    assert target_transport.requests == []


def test_iterator_is_lazy_and_traverses_pages_incrementally() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport((collection_record(),), continuation),
            Page((collection_record("second"),)),
        ]
    )
    iterator = ConfigManager(transport=transport).collections.iter()
    assert transport.requests == []
    assert next(iterator).id == "SMS00001"
    assert len(transport.requests) == 1
    assert next(iterator).id == "second"
    assert len(transport.requests) == 2


def test_retained_manager_respects_client_lifecycle() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    collections = client.collections
    client.close()
    with pytest.raises(LifecycleError):
        collections.list()
    with pytest.raises(LifecycleError):
        collections.get("SMS00001")
    with pytest.raises(LifecycleError):
        next(collections.iter())
    assert transport.requests == [] and transport.key_requests == []
