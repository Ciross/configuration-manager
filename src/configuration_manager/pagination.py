"""Typed, materialized pagination values."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True, slots=True)
class Continuation:
    """Internal transport-owned state; consumers must not interpret it."""

    _value: object = field(repr=False)


@dataclass(frozen=True, slots=True, init=False)
class Page(Generic[T_co]):
    """One materialized service page with opaque continuation state.

    A page never performs I/O and deliberately exposes neither a next-link nor a
    client-controlled page-size concept.
    """

    items: tuple[T_co, ...]
    _continuation: Continuation | None = field(default=None, repr=False)

    def __init__(
        self,
        items: Iterable[T_co],
        *,
        _continuation: Continuation | None = None,
    ) -> None:
        """Materialize ``items`` into an immutable tuple."""
        object.__setattr__(self, "items", tuple(items))
        object.__setattr__(self, "_continuation", _continuation)

    @property
    def has_next(self) -> bool:
        """Return whether the originating transport reported another page."""
        return self._continuation is not None
