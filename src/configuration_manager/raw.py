"""Public low-level provider facades."""

# Facades consume lifecycle/pagination internals without exposing them.
# pyright: reportPrivateUsage=false

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from .pagination import Page
from .transport import (
    AdminServiceSurface,
    EntityQuery,
    ODataQueryOptions,
    RawRecord,
    _Continuation,
)

if TYPE_CHECKING:
    from .client import ConfigManager


class RawWmi:
    """Read-only AdminService ``/wmi`` collection queries."""

    __slots__ = ("_client",)

    def __init__(self, client: "ConfigManager") -> None:
        self._client = client

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
                AdminServiceSurface.WMI,
                entity,
                ODataQueryOptions(filter, select, expand, order_by, top),
            )
        )

    def next_page(self, page: Page[RawRecord]) -> Page[RawRecord]:
        transport = self._client._provider_transport()
        if page._continuation is None:
            raise ValueError("page has no continuation")
        continuation = cast("_Continuation", page._continuation)
        return transport.query_entities(
            EntityQuery(AdminServiceSurface.WMI, "", continuation=continuation)
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


class Raw:
    """Low-level ConfigMgr provider namespaces."""

    __slots__ = ("wmi",)

    def __init__(self, client: "ConfigManager") -> None:
        self.wmi = RawWmi(client)
