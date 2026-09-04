"""Unit coverage for User mapping and resource operations."""

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
    User,
)
from configuration_manager.resources.users import _map_user
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
        self.entity: RawRecord | None = {"ResourceId": 1}

    def query_entities(self, request: EntityQuery) -> RawPage:
        self.requests.append(request)
        return self.pages.pop(0) if self.pages else Page(({"ResourceId": 1},))

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        self.key_requests.append(request)
        return self.entity

    def query_navigation(self, request: NavigationQuery) -> RawPage | None:
        raise AssertionError("not used")

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise AssertionError("not used")

    def close(self) -> None:
        pass


def test_complete_payload_maps_to_frozen_slotted_user() -> None:
    user = _map_user(
        {
            "ResourceId": 2063597568,
            "Name": r"CONTOSO\alice (Alice Example)",
            "UniqueUserName": r"CONTOSO\alice",
            "UserName": "alice",
            "FullUserName": "Alice Example",
            "Mail": "alice@example.com",
            "WindowsNTDomain": "CONTOSO",
            "SID": "S-1-5-21-...",
            "DistinguishedName": "CN=Alice Example,OU=Users,DC=contoso,DC=com",
            "IgnoredFutureProperty": "future",
        }
    )
    assert user == User(
        2063597568,
        r"CONTOSO\alice (Alice Example)",
        r"CONTOSO\alice",
        "alice",
        "Alice Example",
        "alice@example.com",
        "CONTOSO",
        "S-1-5-21-...",
        "CN=Alice Example,OU=Users,DC=contoso,DC=com",
    )
    with pytest.raises(FrozenInstanceError):
        user.name = "changed"  # type: ignore[misc]
    assert not hasattr(user, "__dict__")


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "1", [], {}])
def test_invalid_resource_id_is_rejected(value: object) -> None:
    with pytest.raises(QueryError, match="ResourceId"):
        _map_user({"ResourceId": value})  # type: ignore[dict-item]


def test_resource_id_casing_is_strict() -> None:
    with pytest.raises(QueryError, match="ResourceId"):
        _map_user({"ResourceID": 123})


@pytest.mark.parametrize(
    "field",
    [
        "Name",
        "UniqueUserName",
        "UserName",
        "FullUserName",
        "Mail",
        "WindowsNTDomain",
        "SID",
        "DistinguishedName",
    ],
)
def test_optional_strings_support_missing_null_and_exact_strings(field: str) -> None:
    assert getattr(_map_user({"ResourceId": 1}), _attribute(field)) is None
    assert getattr(_map_user({"ResourceId": 1, field: None}), _attribute(field)) is None
    assert (
        getattr(_map_user({"ResourceId": 1, field: "  VaLuE  "}), _attribute(field))
        == "  VaLuE  "
    )
    with pytest.raises(QueryError, match=field):
        _map_user({"ResourceId": 1, field: 3})


def _attribute(field: str) -> str:
    return {
        "Name": "name",
        "UniqueUserName": "unique_username",
        "UserName": "username",
        "FullUserName": "full_name",
        "Mail": "email",
        "WindowsNTDomain": "domain",
        "SID": "sid",
        "DistinguishedName": "distinguished_name",
    }[field]


def test_list_and_get_send_exact_wmi_queries() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    assert client.users.list(limit=10).items == (User(1),)
    assert client.users.get(2063597568) == User(1)
    assert transport.requests == [
        EntityQuery(
            surface=AdminServiceSurface.WMI,
            entity="SMS_R_User",
            options=ODataQueryOptions(
                select=(
                    "ResourceId",
                    "Name",
                    "UniqueUserName",
                    "UserName",
                    "FullUserName",
                    "Mail",
                    "WindowsNTDomain",
                    "SID",
                    "DistinguishedName",
                ),
                top=10,
            ),
        )
    ]
    assert transport.key_requests == [
        EntityKeyQuery(
            surface=AdminServiceSurface.WMI,
            entity="SMS_R_User",
            key=2063597568,
            options=ODataQueryOptions(
                select=(
                    "ResourceId",
                    "Name",
                    "UniqueUserName",
                    "UserName",
                    "FullUserName",
                    "Mail",
                    "WindowsNTDomain",
                    "SID",
                    "DistinguishedName",
                ),
            ),
        )
    ]


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1"])
def test_invalid_inputs_do_not_call_provider(value: object) -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    with pytest.raises(ValueError):
        client.users.list(limit=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        client.users.get(value)  # type: ignore[arg-type]
    assert transport.requests == transport.key_requests == []


def test_get_none_is_rbac_safe_not_found() -> None:
    transport = FakeTransport()
    transport.entity = None
    with pytest.raises(NotFoundError, match="not visible"):
        ConfigManager(transport=transport).users.get(1)


def test_pagination_is_owned_and_iterator_is_lazy() -> None:
    continuation = _Continuation(object())
    transport = FakeTransport(
        [
            Page[RawRecord]._from_transport(
                ({"ResourceId": 1}, {"ResourceId": 2}), continuation
            ),
            Page(({"ResourceId": 3},)),
        ]
    )
    client = ConfigManager(transport=transport)
    iterator = client.users.iter()
    assert transport.requests == []
    assert next(iterator) == User(1)
    assert len(transport.requests) == 1
    assert next(iterator) == User(2)
    assert len(transport.requests) == 1
    assert next(iterator) == User(3)
    assert transport.requests[1] == EntityQuery(
        AdminServiceSurface.WMI, "SMS_R_User", continuation=continuation
    )


def test_foreign_raw_and_continuationless_pages_are_rejected_without_io() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    other_transport = FakeTransport(
        [Page[RawRecord]._from_transport(({"ResourceId": 1},), _Continuation(object()))]
    )
    foreign = ConfigManager(transport=other_transport).users.list()
    for page in (
        foreign,
        Page((User(1),)),
        Page[RawRecord]._from_transport(({"ResourceId": 1},), _Continuation(object())),
    ):
        with pytest.raises(ValueError):
            client.users.next_page(page)  # type: ignore[arg-type]
    assert transport.requests == []


def test_closed_client_operations_and_lazy_iterator_fail_without_io() -> None:
    transport = FakeTransport()
    client = ConfigManager(transport=transport)
    iterator = client.users.iter()
    client.close()
    for operation in (
        client.users.list,
        lambda: client.users.get(1),
        lambda: next(iterator),
    ):
        with pytest.raises(LifecycleError):
            operation()
    assert transport.requests == transport.key_requests == []
