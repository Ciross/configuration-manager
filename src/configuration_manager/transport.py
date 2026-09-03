"""Provider-shaped values and the synchronous capability boundary."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, TypeAlias

from .pagination import Page

JsonScalar: TypeAlias = bool | int | float | str | None
JsonNonNullScalar: TypeAlias = bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
RawRecord: TypeAlias = Mapping[str, JsonValue]
RawMethodResult: TypeAlias = JsonValue
RawPage: TypeAlias = Page[RawRecord]


def _empty_parameters() -> Mapping[str, JsonValue]:
    return MappingProxyType({})


def _validate_non_null_key(value: object) -> None:
    if value is None:
        raise ValueError("entity key must not be None")


@dataclass(frozen=True, slots=True)
class _Continuation:
    """Opaque state understood only by its originating transport."""

    _value: object = field(repr=False)


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
    continuation: _Continuation | None = None


@dataclass(frozen=True, slots=True)
class EntityKeyQuery:
    """Request one entity by its provider key."""

    surface: AdminServiceSurface
    entity: str
    key: JsonNonNullScalar
    options: ODataQueryOptions = ODataQueryOptions()

    def __post_init__(self) -> None:
        """Reject a null provider key even at untyped runtime boundaries."""
        _validate_non_null_key(self.key)


@dataclass(frozen=True, slots=True)
class NavigationQuery:
    """Request a collection navigation property from one keyed entity."""

    surface: AdminServiceSurface
    entity: str
    key: JsonNonNullScalar
    navigation: str
    options: ODataQueryOptions = ODataQueryOptions()
    continuation: _Continuation | None = None

    def __post_init__(self) -> None:
        """Reject a null root key even at untyped runtime boundaries."""
        _validate_non_null_key(self.key)


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
    key: JsonNonNullScalar | None = None
    parameters: Mapping[str, JsonValue] = field(default_factory=_empty_parameters)

    def __post_init__(self) -> None:
        """Reject structurally invalid names and method target/key combinations."""
        if not self.entity.strip():
            raise ValueError("entity must not be empty")
        if not self.method.strip():
            raise ValueError("method must not be empty")
        if self.target is MethodTarget.STATIC and self.key is not None:
            raise ValueError("a static method call must not have an entity key")
        if self.target is MethodTarget.INSTANCE and self.key is None:
            raise ValueError("an instance method call requires an entity key")


class ProviderTransport(Protocol):
    """Advanced, synchronous provider capability injection contract.

    This pre-1.0 protocol intentionally contains no HTTP or authentication API.
    """

    def query_entities(self, request: EntityQuery) -> RawPage: ...

    def query_navigation(self, request: NavigationQuery) -> RawPage | None: ...

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None: ...

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult: ...

    def close(self) -> None: ...
