"""Unit coverage for typed User-to-Collection memberships."""

# Private values are used to construct controlled provider continuations.
# pyright: reportPrivateUsage=false

from dataclasses import FrozenInstanceError

import pytest

from configuration_manager import (
    ConfigManager,
    LifecycleError,
    NotFoundError,
    Page,
    QueryError,
    UserCollectionMembership,
)
from configuration_manager.resources.users import _map_user_collection_membership
from configuration_manager.transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
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
        self.entity: RawRecord | None = {"ResourceId": 2063597568}

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        return self.pages.pop(0) if self.pages else Page(())

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.key_requests.append(request)
        return self.entity

    def query_navigation(self, request: NavigationQuery) -> RawPage | None:
        raise AssertionError("not used")

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        pass


def record(user_id: int = 2063597568) -> RawRecord:
    return {
        "CollectionID": "SMS00002",
        "ResourceID": user_id,
        "ResourceType": 4,
        "Name": r"EU\svc-SDAutomation (svc-SDAutomation)",
        "IgnoredFutureProperty": "future",
    }


def test_model_and_mapper_are_strict_frozen_and_slotted() -> None:
    membership = _map_user_collection_membership(record(), 2063597568)
    assert membership == UserCollectionMembership(2063597568, "SMS00002")
    assert not hasattr(membership, "__dict__")
    with pytest.raises(FrozenInstanceError):
        membership.collection_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "2063597568", [], {}])
def test_invalid_membership_resource_id(value: object) -> None:
    payload = record()
    payload["ResourceID"] = value  # type: ignore[assignment]
    with pytest.raises(QueryError, match="positive integer"):
        _map_user_collection_membership(payload, 2063597568)


def test_mismatched_membership_resource_id() -> None:
    with pytest.raises(QueryError, match="does not match"):
        _map_user_collection_membership(record(1), 2063597568)


@pytest.mark.parametrize("value", [None, "", "   ", 1, True, [], {}])
def test_invalid_membership_collection_id(value: object) -> None:
    payload = record()
    payload["CollectionID"] = value  # type: ignore[assignment]
    with pytest.raises(QueryError, match="CollectionID"):
        _map_user_collection_membership(payload, 2063597568)


@pytest.mark.parametrize("value", [None, True, False, 0, 1, 2, 3, 5, 1.5, "4", [], {}])
def test_invalid_membership_resource_type(value: object) -> None:
    payload = record()
    payload["ResourceType"] = value  # type: ignore[assignment]
    with pytest.raises(QueryError, match="ResourceType"):
        _map_user_collection_membership(payload, 2063597568)


def test_aliases_are_not_accepted() -> None:
    with pytest.raises(QueryError, match="ResourceID"):
        _map_user_collection_membership(
            {"ResourceId": 2063597568, "CollectionID": "SMS00002", "ResourceType": 4},
            2063597568,
        )
    with pytest.raises(QueryError, match="CollectionID"):
        _map_user_collection_membership(
            {"ResourceID": 2063597568, "CollectionId": "SMS00002", "ResourceType": 4},
            2063597568,
        )


def test_initial_query_validates_root_and_maps_empty_page() -> None:
    transport = FakeTransport([Page(())])
    client = ConfigManager(transport=transport)
    page = client.users.collection_memberships(2063597568, limit=10)
    assert page.items == () and not page.has_next
    assert len(transport.key_requests) == 1
    assert transport.requests == [
        EntityQuery(
            AdminServiceSurface.WMI,
            "SMS_FullCollectionMembership",
            options=ODataQueryOptions(
                filter="ResourceID eq 2063597568",
                select=("CollectionID", "ResourceID", "ResourceType"),
                top=10,
            ),
        )
    ]


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1"])
def test_invalid_inputs_short_circuit(value: object) -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    with pytest.raises(ValueError):
        client.users.collection_memberships(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        client.users.collection_memberships(1, limit=value)  # type: ignore[arg-type]
    assert transport.requests == transport.key_requests == []


def test_missing_or_malformed_root_short_circuits() -> None:
    transport = FakeTransport()
    transport.entity = None
    with pytest.raises(NotFoundError):
        ConfigManager(transport=transport).users.collection_memberships(1)
    assert transport.requests == []
    transport.entity = {"ResourceId": 0}
    with pytest.raises(QueryError):
        ConfigManager(transport=transport).users.collection_memberships(1)
    assert transport.requests == []


def test_continuation_is_owned_preserves_id_and_iterator_is_lazy() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport((record(), record()), continuation),
            Page((record(),)),
        ]
    )
    client = ConfigManager(transport=transport)
    iterator = client.users.iter_collection_memberships(2063597568)
    assert transport.requests == transport.key_requests == []
    assert next(iterator).collection_id == "SMS00002"
    assert len(transport.requests) == len(transport.key_requests) == 1
    next(iterator)
    assert len(transport.requests) == 1
    next(iterator)
    assert len(transport.key_requests) == 1
    assert transport.requests[1] == EntityQuery(
        AdminServiceSurface.WMI,
        "SMS_FullCollectionMembership",
        continuation=continuation,
    )


def test_invalid_pages_and_closed_operations_do_no_io() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    raw_page = Page[RawRecord]._from_transport((), _Continuation(object()))
    for page in (Page(()), raw_page):
        with pytest.raises(ValueError):
            client.users.next_collection_memberships_page(page)  # type: ignore[arg-type]
    iterator = client.users.iter_collection_memberships(1)
    client.close()
    with pytest.raises(LifecycleError):
        client.users.collection_memberships(1)
    with pytest.raises(LifecycleError):
        next(iterator)
    assert transport.requests == transport.key_requests == []
