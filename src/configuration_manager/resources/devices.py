"""Read-only high-level Device resources."""

# Resource pagination deliberately consumes package-private continuation state.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, cast

from ..exceptions import NotFoundError, QueryError
from ..models import Device
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
class _DevicesContinuation:
    owner: object
    continuation: _Continuation


def _optional_string(record: Mapping[str, JsonValue], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise QueryError(f"Device field {field} has an invalid type")
    return value


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
    is_active = record.get("IsActive")
    if is_active is not None and not isinstance(is_active, bool):
        raise QueryError("Device field IsActive has an invalid type")
    return Device(
        id=machine_id,
        name=_optional_string(record, "Name"),
        client_version=_optional_string(record, "ClientVersion"),
        operating_system=_optional_string(record, "DeviceOS"),
        is_active=is_active,
        last_active_time=_last_active_time(record),
    )


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
