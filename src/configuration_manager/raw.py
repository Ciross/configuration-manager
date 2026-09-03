"""Public low-level provider facades."""

# Facades consume lifecycle/pagination internals without exposing them.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from .pagination import Page
from .transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    JsonNonNullScalar,
    ODataQueryOptions,
    RawRecord,
    _Continuation,
)

if TYPE_CHECKING:
    from .client import ConfigManager


class _RawEntitySurface:
    """Shared mechanics for one read-only AdminService entity surface."""

    __slots__ = ("_client", "_surface")

    def __init__(self, client: "ConfigManager", surface: AdminServiceSurface) -> None:
        self._client = client
        self._surface = surface

    def query(
        self,
        entity: str,
        *,
        filter: str | None = None,
        select: tuple[str, ...] = (),
        expand: tuple[str, ...] = (),
        order_by: tuple[str, ...] = (),
        top: int | None = None,
    ) -> Page[RawRecord]:
        transport = self._client._provider_transport()
        return transport.query_entities(
            EntityQuery(
                self._surface,
                entity,
                ODataQueryOptions(filter, select, expand, order_by, top),
            )
        )

    def get(
        self,
        entity: str,
        key: JsonNonNullScalar,
        *,
        select: tuple[str, ...] = (),
        expand: tuple[str, ...] = (),
    ) -> RawRecord | None:
        """Return one keyed WMI entity, or ``None`` when it is not visible."""
        transport = self._client._provider_transport()
        return transport.get_entity(
            EntityKeyQuery(
                surface=self._surface,
                entity=entity,
                key=key,
                options=ODataQueryOptions(select=select, expand=expand),
            )
        )

    def next_page(self, page: Page[RawRecord]) -> Page[RawRecord]:
        transport = self._client._provider_transport()
        if page._continuation is None:
            raise ValueError("page has no continuation")
        continuation = cast("_Continuation", page._continuation)
        return transport.query_entities(
            EntityQuery(self._surface, "", continuation=continuation)
        )

    def iter(
        self,
        entity: str,
        *,
        filter: str | None = None,
        select: tuple[str, ...] = (),
        expand: tuple[str, ...] = (),
        order_by: tuple[str, ...] = (),
        top: int | None = None,
    ) -> Iterator[RawRecord]:
        page = self.query(
            entity,
            filter=filter,
            select=select,
            expand=expand,
            order_by=order_by,
            top=top,
        )
        while True:
            yield from page.items
            if not page.has_next:
                return
            page = self.next_page(page)


class RawWmi(_RawEntitySurface):
    """Read-only AdminService ``/wmi`` queries."""

    __slots__ = ()

    def __init__(self, client: "ConfigManager") -> None:
        super().__init__(client, AdminServiceSurface.WMI)


class RawV1(_RawEntitySurface):
    """Read-only AdminService ``/v1.0`` queries."""

    __slots__ = ()

    def __init__(self, client: "ConfigManager") -> None:
        super().__init__(client, AdminServiceSurface.V1)


class Raw:
    """Low-level ConfigMgr provider namespaces."""

    __slots__ = ("v1", "wmi")

    def __init__(self, client: "ConfigManager") -> None:
        self.v1 = RawV1(client)
        self.wmi = RawWmi(client)
