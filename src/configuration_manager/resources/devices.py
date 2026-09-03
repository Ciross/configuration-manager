"""Read-only high-level Device resources."""

# Resource pagination deliberately consumes package-private continuation state.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, cast

from ..exceptions import NotFoundError, QueryError
from ..models import Device, DeviceCollectionMembership
from ..pagination import Page
from ..transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonValue,
    NavigationQuery,
    ODataQueryOptions,
    RawPage,
    RawRecord,
    _Continuation,
)

if TYPE_CHECKING:
    from ..client import ConfigManager


@dataclass(frozen=True, slots=True)
class _DevicesContinuation:
    owner: object
    continuation: _Continuation


@dataclass(frozen=True, slots=True)
class _DeviceCollectionMembershipsContinuation:
    owner: object
    device_id: int
    continuation: _Continuation


def _optional_string(record: Mapping[str, JsonValue], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryError(f"Device field {field} has an invalid type")
    return value


def _optional_boolean_flag(record: Mapping[str, JsonValue], field: str) -> bool | None:
    value = record.get(field)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if type(value) is int:
        if value == 0:
            return False
        if value == 1:
            return True
    raise QueryError(f"Device field {field} has an invalid type")


def _last_active_time(record: Mapping[str, JsonValue]) -> datetime | None:
    value = record.get("LastActiveTime")
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryError("Device field LastActiveTime has an invalid type")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QueryError(
            "Device field LastActiveTime is not a valid timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QueryError("Device field LastActiveTime must include a timezone")
    return parsed


def _map_device(record: RawRecord) -> Device:
    """Map one raw v1 record to a validated domain model."""
    machine_id = record.get("MachineId")
    if not isinstance(machine_id, int) or isinstance(machine_id, bool):
        raise QueryError("Device field MachineId must be an integer")
    return Device(
        id=machine_id,
        name=_optional_string(record, "Name"),
        client_version=_optional_string(record, "ClientVersion"),
        operating_system=_optional_string(record, "DeviceOS"),
        is_active=_optional_boolean_flag(record, "IsActive"),
        last_active_time=_last_active_time(record),
    )


def _map_device_collection_membership(
    record: RawRecord, device_id: int
) -> DeviceCollectionMembership:
    """Map one expanded v1 relationship record to its domain model."""
    collection_value = record.get("Collection")
    if not isinstance(collection_value, Mapping):
        raise QueryError(
            "Device collection membership field Collection must be an object"
        )
    collection = cast("Mapping[object, object]", collection_value)
    collection_id = collection.get("CollectionID")
    if not isinstance(collection_id, str) or not collection_id.strip():
        raise QueryError(
            "Device collection membership field Collection.CollectionID must be a "
            "non-empty string"
        )
    name = collection.get("Name")
    if name is not None and not isinstance(name, str):
        raise QueryError(
            "Device collection membership field Collection.Name has an invalid type"
        )
    return DeviceCollectionMembership(device_id, collection_id, name)


class Devices:
    """Read-only access to versioned AdminService Device entities."""

    __slots__ = ("_client",)

    def __init__(self, client: "ConfigManager") -> None:
        self._client = client

    def _map_page(self, raw_page: RawPage) -> Page[Device]:
        items = tuple(_map_device(record) for record in raw_page.items)
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[Device]._from_transport(
            items, _DevicesContinuation(self, continuation)
        )

    def _map_collection_memberships_page(
        self, raw_page: RawPage, device_id: int
    ) -> Page[DeviceCollectionMembership]:
        items = tuple(
            _map_device_collection_membership(record, device_id)
            for record in raw_page.items
        )
        if raw_page._continuation is None:
            return Page(items)
        continuation = cast("_Continuation", raw_page._continuation)
        return Page[DeviceCollectionMembership]._from_transport(
            items,
            _DeviceCollectionMembershipsContinuation(self, device_id, continuation),
        )

    def list(self, *, limit: int | None = None) -> Page[Device]:
        """Return one server-controlled page of devices."""
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
                    surface=AdminServiceSurface.V1,
                    entity="Device",
                    options=ODataQueryOptions(top=limit),
                )
            )
        )

    def get(self, id: int) -> Device:
        """Return one device by its positive integer ConfigMgr resource ID."""
        if (
            not isinstance(id, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(id, bool)
            or id <= 0
        ):
            raise ValueError("id must be a positive integer")
        transport = self._client._provider_transport()
        record = transport.get_entity(
            EntityKeyQuery(AdminServiceSurface.V1, "Device", id)
        )
        if record is None:
            raise NotFoundError(
                "Device was not found or is not visible to the current identity"
            )
        return _map_device(record)

    def collection_memberships(
        self, id: int, *, limit: int | None = None
    ) -> Page[DeviceCollectionMembership]:
        """Return one page of collections to which a device belongs."""
        self._validate_id(id)
        if limit is not None and (
            not isinstance(limit, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(limit, bool)
            or limit <= 0
        ):
            raise ValueError("limit must be a positive integer or None")
        transport = self._client._provider_transport()
        raw_page = transport.query_navigation(
            NavigationQuery(
                surface=AdminServiceSurface.V1,
                entity="Device",
                key=id,
                navigation="ResourceCollectionMembership",
                options=ODataQueryOptions(
                    select=("Collection",), expand=("Collection",), top=limit
                ),
            )
        )
        if raw_page is None:
            raise NotFoundError(
                "Device was not found or is not visible to the current identity"
            )
        return self._map_collection_memberships_page(raw_page, id)

    def next_collection_memberships_page(
        self, page: Page[DeviceCollectionMembership]
    ) -> Page[DeviceCollectionMembership]:
        """Return the next membership page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if (
            not isinstance(wrapped, _DeviceCollectionMembershipsContinuation)
            or wrapped.owner is not self
        ):
            raise ValueError("page did not originate from this Devices manager")
        transport = self._client._provider_transport()
        raw_page = transport.query_navigation(
            NavigationQuery(
                surface=AdminServiceSurface.V1,
                entity="Device",
                key=wrapped.device_id,
                navigation="ResourceCollectionMembership",
                continuation=wrapped.continuation,
            )
        )
        if raw_page is None:
            raise QueryError("Device collection membership continuation was not found")
        return self._map_collection_memberships_page(raw_page, wrapped.device_id)

    def iter_collection_memberships(
        self, id: int
    ) -> Iterator[DeviceCollectionMembership]:
        """Traverse a device's collection memberships lazily."""
        page = self.collection_memberships(id)
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_collection_memberships_page(page)

    @staticmethod
    def _validate_id(id: int) -> None:
        if (
            not isinstance(id, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(id, bool)
            or id <= 0
        ):
            raise ValueError("id must be a positive integer")

    def next_page(self, page: Page[Device]) -> Page[Device]:
        """Return the next page produced by this manager."""
        if page._continuation is None:
            raise ValueError("page has no continuation")
        wrapped = page._continuation
        if not isinstance(wrapped, _DevicesContinuation) or wrapped.owner is not self:
            raise ValueError("page did not originate from this Devices manager")
        transport = self._client._provider_transport()
        return self._map_page(
            transport.query_entities(
                EntityQuery(
                    surface=AdminServiceSurface.V1,
                    entity="Device",
                    continuation=wrapped.continuation,
                )
            )
        )

    def iter(self) -> Iterator[Device]:
        """Traverse devices lazily, following server pagination."""
        page = self.list()
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_page(page)
