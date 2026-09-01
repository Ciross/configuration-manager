"""Provider-shaped values and the synchronous capability boundary."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, TypeAlias

from .pagination import Continuation, Page

JsonScalar: TypeAlias = bool | int | float | str | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
RawRecord: TypeAlias = Mapping[str, JsonValue]
RawMethodResult: TypeAlias = JsonValue
RawPage: TypeAlias = Page[RawRecord]


def _empty_parameters() -> Mapping[str, JsonValue]:
    return MappingProxyType({})


class AdminServiceSurface(StrEnum):
    """An AdminService HTTPS/OData surface (never direct WMI/DCOM)."""

    V1 = "v1.0"
    WMI = "wmi"


@dataclass(frozen=True, slots=True)
class ODataQueryOptions:
    """Structural OData query options; ``top`` is a result limit, not page size."""

    filter: str | None = None
    select: tuple[str, ...] = ()
    expand: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    top: int | None = None

    def __post_init__(self) -> None:
        """Reject locally invalid option shapes without schema assumptions."""
        if self.top is not None and self.top <= 0:
            raise ValueError("top must be positive")
        for names in (self.select, self.expand, self.order_by):
            if any(not name.strip() for name in names):
                raise ValueError("query option property names must not be empty")


@dataclass(frozen=True, slots=True)
class EntityQuery:
    """Request one provider-controlled page of an entity or provider class."""

    surface: AdminServiceSurface
    entity: str
    options: ODataQueryOptions = ODataQueryOptions()
    continuation: Continuation | None = None


@dataclass(frozen=True, slots=True)
class EntityKeyQuery:
    """Request one entity by its provider key."""

    surface: AdminServiceSurface
    entity: str
    key: JsonScalar
    options: ODataQueryOptions = ODataQueryOptions()


class MethodTarget(StrEnum):
    """The provider-level target kind for a named method."""

    STATIC = "static"
    INSTANCE = "instance"


@dataclass(frozen=True, slots=True)
class ProviderMethodCall:
    """Request invocation of a named provider method."""

    surface: AdminServiceSurface
    entity: str
    method: str
    target: MethodTarget
    key: JsonScalar = None
    parameters: Mapping[str, JsonValue] = field(default_factory=_empty_parameters)


class ProviderTransport(Protocol):
    """Advanced, synchronous provider capability injection contract.

    This pre-1.0 protocol intentionally contains no HTTP or authentication API.
    """

    def query_entities(self, request: EntityQuery) -> RawPage: ...

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None: ...

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult: ...

    def close(self) -> None: ...
