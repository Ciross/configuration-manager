"""Read-only high-level Collection resources."""

# Resource pagination deliberately consumes package-private continuation state.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..exceptions import NotFoundError, QueryError
from ..models import Collection, CollectionDeviceMember, CollectionType
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


@dataclass(frozen=True, slots=True)
class _CollectionsContinuation:
    owner: object
    continuation: _Continuation


@dataclass(frozen=True, slots=True)
class _CollectionDeviceMembersContinuation:
    owner: object
    collection_id: str
    continuation: _Continuation


def _odata_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _optional_string(record: Mapping[str, JsonValue], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryError(f"Collection field {field} has an invalid type")
    return value


def _map_collection(record: RawRecord) -> Collection:
    """Map one raw WMI record to a validated domain model."""
    collection_id = record.get("CollectionID")
    if not isinstance(collection_id, str) or not collection_id.strip():
        raise QueryError("Collection field CollectionID must be a non-empty string")

    raw_type = record.get("CollectionType")
    if isinstance(raw_type, bool) or not isinstance(raw_type, int):
        raise QueryError("Collection field CollectionType has an invalid value")
    try:
        collection_type = CollectionType(raw_type)
    except ValueError as error:
        raise QueryError(
            "Collection field CollectionType has an invalid value"
        ) from error

    member_count = record.get("MemberCount")
    if member_count is not None and (
        isinstance(member_count, bool)
        or not isinstance(member_count, int)
        or member_count < 0
    ):
        raise QueryError("Collection field MemberCount has an invalid value")

    is_builtin = record.get("IsBuiltIn")
    if is_builtin is not None and not isinstance(is_builtin, bool):
        raise QueryError("Collection field IsBuiltIn has an invalid type")

    return Collection(
        id=collection_id,
        name=_optional_string(record, "Name"),
        collection_type=collection_type,
        member_count=member_count,
        limiting_collection_id=_optional_string(record, "LimitToCollectionID"),
        limiting_collection_name=_optional_string(record, "LimitToCollectionName"),
        is_builtin=is_builtin,
    )


def _map_collection_device_member(
    record: RawRecord, collection_id: str
) -> CollectionDeviceMember:
    """Map one WMI collection-membership record to its relationship model."""
    returned_collection_id = record.get("CollectionID")
    if (
        not isinstance(returned_collection_id, str)
        or not returned_collection_id.strip()
    ):
        raise QueryError(
            "Collection device member field CollectionID must be a non-empty string"
        )
    if returned_collection_id != collection_id:
        raise QueryError(
            "Collection device member field CollectionID does not match the query"
        )

    device_id = record.get("ResourceID")
    if isinstance(device_id, bool) or not isinstance(device_id, int) or device_id <= 0:
        raise QueryError(
            "Collection device member field ResourceID must be a positive integer"
        )

    device_name = record.get("Name")
    if device_name is not None and not isinstance(device_name, str):
        raise QueryError("Collection device member field Name has an invalid type")
    return CollectionDeviceMember(returned_collection_id, device_id, device_name)


class Collections:
    """Read-only access to AdminService WMI SMS_Collection entities."""

    __slots__ = ("_client",)

    def __init__(self, client: "ConfigManager") -> None:
        self._client = client

    def _map_page(self, raw_page: RawPage) -> Page[Collection]:
        items = tuple(_map_collection(record) for record in raw_page.items)
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[Collection]._from_transport(
            items, _CollectionsContinuation(self, continuation)
        )

    def _map_device_members_page(
        self, raw_page: RawPage, collection_id: str
    ) -> Page[CollectionDeviceMember]:
        items = tuple(
            _map_collection_device_member(record, collection_id)
            for record in raw_page.items
        )
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[CollectionDeviceMember]._from_transport(
            items,
            _CollectionDeviceMembersContinuation(self, collection_id, continuation),
        )

    def list(self, *, limit: int | None = None) -> Page[Collection]:
        """Return one server-controlled page of collections."""
        if limit is not None and (
            not isinstance(limit, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(limit, bool)
            or limit <= 0
        ):
            raise ValueError("limit must be a positive integer or None")
        transport = self._client._provider_transport()
        return self._map_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_Collection",
                    options=ODataQueryOptions(top=limit),
                )
            )
        )

    def get(self, id: str) -> Collection:
        """Return one collection by its provider identifier."""
        if not isinstance(id, str) or not id.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("id must be a non-empty string")
        transport = self._client._provider_transport()
        record = transport.get_entity(
            EntityKeyQuery(AdminServiceSurface.WMI, "SMS_Collection", id)
        )
        if record is None:
            raise NotFoundError(
                "Collection was not found or is not visible to the current identity"
            )
        return _map_collection(record)

    def device_members(
        self, id: str, *, limit: int | None = None
    ) -> Page[CollectionDeviceMember]:
        """Return one page of device members for a Device collection."""
        self._validate_id(id)
        if limit is not None and (
            not isinstance(limit, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(limit, bool)
            or limit <= 0
        ):
            raise ValueError("limit must be a positive integer or None")
        collection = self.get(id)
        if collection.collection_type is not CollectionType.DEVICE:
            raise ValueError("collection must be a device collection")
        transport = self._client._provider_transport()
        return self._map_device_members_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_FullCollectionMembership",
                    options=ODataQueryOptions(
                        filter=f"CollectionID eq {_odata_string_literal(id)}",
                        select=("CollectionID", "ResourceID", "Name"),
                        top=limit,
                    ),
                )
            ),
            id,
        )

    def next_device_members_page(
        self, page: Page[CollectionDeviceMember]
    ) -> Page[CollectionDeviceMember]:
        """Return the next device-member page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if (
            not isinstance(wrapped, _CollectionDeviceMembersContinuation)
            or wrapped.owner is not self
        ):
            raise ValueError("page did not originate from this Collections manager")
        transport = self._client._provider_transport()
        return self._map_device_members_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.WMI,
                    entity="SMS_FullCollectionMembership",
                    continuation=wrapped.continuation,
                )
            ),
            wrapped.collection_id,
        )

    def iter_device_members(self, id: str) -> Iterator[CollectionDeviceMember]:
        """Traverse a collection's device members lazily."""
        page = self.device_members(id)
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_device_members_page(page)

    @staticmethod
    def _validate_id(id: str) -> None:
        if not isinstance(id, str) or not id.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("id must be a non-empty string")

    def next_page(self, page: Page[Collection]) -> Page[Collection]:
        """Return the next page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if (
            not isinstance(wrapped, _CollectionsContinuation)
            or wrapped.owner is not self
        ):
            raise ValueError("page did not originate from this Collections manager")
        transport = self._client._provider_transport()
        return self._map_page(
            transport.query_entities(
                EntityQuery(
                    AdminServiceSurface.WMI,
                    "SMS_Collection",
                    continuation=wrapped.continuation,
                )
            )
        )

    def iter(self) -> Iterator[Collection]:
        """Traverse collections lazily, following server pagination."""
        page = self.list()
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_page(page)
