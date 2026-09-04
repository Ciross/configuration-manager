"""Read-only high-level User resources."""

# Resource pagination deliberately consumes package-private continuation state.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..exceptions import NotFoundError, QueryError
from ..models import User, UserCollectionMembership
from ..pagination import Page
from ..transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonValue,
    ODataQueryOptions,
    RawPage,
    RawRecord,
    _Continuation,
)

if TYPE_CHECKING:
    from ..client import ConfigManager


_USER_SELECT = (
    "ResourceId",
    "Name",
    "UniqueUserName",
    "UserName",
    "FullUserName",
    "Mail",
    "WindowsNTDomain",
    "SID",
    "DistinguishedName",
)

_USER_COLLECTION_MEMBERSHIP_SELECT = (
    "CollectionID",
    "ResourceID",
    "ResourceType",
)


@dataclass(frozen=True, slots=True)
class _UsersContinuation:
    owner: object
    continuation: _Continuation


@dataclass(frozen=True, slots=True)
class _UserCollectionMembershipsContinuation:
    owner: object
    user_id: int
    continuation: _Continuation


def _optional_string(record: Mapping[str, JsonValue], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryError(f"User field {field} has an invalid type")
    return value


def _map_user(record: RawRecord) -> User:
    """Map one raw SMS_R_User record to a validated domain model."""
    resource_id = record.get("ResourceId")
    if type(resource_id) is not int or resource_id <= 0:
        raise QueryError("User field ResourceId must be a positive integer")
    return User(
        id=resource_id,
        name=_optional_string(record, "Name"),
        unique_username=_optional_string(record, "UniqueUserName"),
        username=_optional_string(record, "UserName"),
        full_name=_optional_string(record, "FullUserName"),
        email=_optional_string(record, "Mail"),
        domain=_optional_string(record, "WindowsNTDomain"),
        sid=_optional_string(record, "SID"),
        distinguished_name=_optional_string(record, "DistinguishedName"),
    )


def _map_user_collection_membership(
    record: RawRecord, user_id: int
) -> UserCollectionMembership:
    """Map and validate one SMS_FullCollectionMembership record."""
    resource_id = record.get("ResourceID")
    if type(resource_id) is not int or resource_id <= 0:
        raise QueryError(
            "User collection membership field ResourceID must be a positive integer"
        )
    if resource_id != user_id:
        raise QueryError(
            "User collection membership field ResourceID does not match the query"
        )
    collection_id = record.get("CollectionID")
    if not isinstance(collection_id, str) or not collection_id.strip():
        raise QueryError(
            "User collection membership field CollectionID must be a non-empty string"
        )
    resource_type = record.get("ResourceType")
    if type(resource_type) is not int or resource_type != 4:
        raise QueryError(
            "User collection membership field ResourceType must identify a User "
            "resource"
        )
    return UserCollectionMembership(resource_id, collection_id)


class Users:
    """Read-only access to AdminService WMI SMS_R_User entities."""

    __slots__ = ("_client",)

    def __init__(self, client: "ConfigManager") -> None:
        self._client = client

    def _map_page(self, raw_page: RawPage) -> Page[User]:
        items = tuple(_map_user(record) for record in raw_page.items)
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[User]._from_transport(items, _UsersContinuation(self, continuation))

    def _map_collection_memberships_page(
        self, raw_page: RawPage, user_id: int
    ) -> Page[UserCollectionMembership]:
        items = tuple(
            _map_user_collection_membership(record, user_id)
            for record in raw_page.items
        )
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[UserCollectionMembership]._from_transport(
            items,
            _UserCollectionMembershipsContinuation(self, user_id, continuation),
        )

    def list(self, *, limit: int | None = None) -> Page[User]:
        """Return one server-controlled page of users."""
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("limit must be a positive integer or None")
        transport = self._client._provider_transport()
        return self._map_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_R_User",
                    options=ODataQueryOptions(select=_USER_SELECT, top=limit),
                )
            )
        )

    def get(self, id: int) -> User:
        """Return one user by its positive integer ConfigMgr resource ID."""
        if type(id) is not int or id <= 0:
            raise ValueError("id must be a positive integer")
        transport = self._client._provider_transport()
        record = transport.get_entity(
            EntityKeyQuery(
                surface=AdminServiceSurface.WMI,
                entity="SMS_R_User",
                key=id,
                options=ODataQueryOptions(select=_USER_SELECT),
            )
        )
        if record is None:
            raise NotFoundError(
                "User was not found or is not visible to the current identity"
            )
        return _map_user(record)

    def collection_memberships(
        self, id: int, *, limit: int | None = None
    ) -> Page[UserCollectionMembership]:
        """Return one page of collections to which a user belongs."""
        self._validate_id(id)
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("limit must be a positive integer or None")
        self.get(id)
        transport = self._client._provider_transport()
        return self._map_collection_memberships_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_FullCollectionMembership",
                    options=ODataQueryOptions(
                        filter=f"ResourceID eq {id}",
                        select=_USER_COLLECTION_MEMBERSHIP_SELECT,
                        top=limit,
                    ),
                )
            ),
            id,
        )

    def next_collection_memberships_page(
        self, page: Page[UserCollectionMembership]
    ) -> Page[UserCollectionMembership]:
        """Return the next User membership page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if (
            not isinstance(wrapped, _UserCollectionMembershipsContinuation)
            or wrapped.owner is not self
        ):
            raise ValueError("page did not originate from this Users manager")
        transport = self._client._provider_transport()
        return self._map_collection_memberships_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_FullCollectionMembership",
                    continuation=wrapped.continuation,
                )
            ),
            wrapped.user_id,
        )

    def iter_collection_memberships(
        self, id: int
    ) -> Iterator[UserCollectionMembership]:
        """Traverse a user's collection memberships lazily."""
        page = self.collection_memberships(id)
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_collection_memberships_page(page)

    @staticmethod
    def _validate_id(id: int) -> None:
        if type(id) is not int or id <= 0:
            raise ValueError("id must be a positive integer")

    def next_page(self, page: Page[User]) -> Page[User]:
        """Return the next page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if not isinstance(wrapped, _UsersContinuation) or wrapped.owner is not self:
            raise ValueError("page did not originate from this Users manager")
        transport = self._client._provider_transport()
        return self._map_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_R_User",
                    continuation=wrapped.continuation,
                )
            )
        )

    def iter(self) -> Iterator[User]:
        """Traverse users lazily, following server pagination."""
        page = self.list()
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_page(page)
