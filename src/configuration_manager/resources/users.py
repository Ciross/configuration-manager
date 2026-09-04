"""Read-only high-level User resources."""

# Resource pagination deliberately consumes package-private continuation state.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ..exceptions import NotFoundError, QueryError
from ..models import User
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
class _UsersContinuation:
    owner: object
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
                    options=ODataQueryOptions(top=limit),
                )
            )
        )

    def get(self, id: int) -> User:
        """Return one user by its positive integer ConfigMgr resource ID."""
        if type(id) is not int or id <= 0:
            raise ValueError("id must be a positive integer")
        transport = self._client._provider_transport()
        record = transport.get_entity(
            EntityKeyQuery(AdminServiceSurface.WMI, "SMS_R_User", id)
        )
        if record is None:
            raise NotFoundError(
                "User was not found or is not visible to the current identity"
            )
        return _map_user(record)

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
