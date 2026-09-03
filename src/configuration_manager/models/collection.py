"""Collection domain model."""

from dataclasses import dataclass
from enum import IntEnum


class CollectionType(IntEnum):
    """The documented Configuration Manager collection types."""

    OTHER = 0
    USER = 1
    DEVICE = 2


@dataclass(frozen=True, slots=True)
class Collection:
    """An immutable Configuration Manager collection."""

    id: str
    name: str | None
    collection_type: CollectionType
    member_count: int | None = None
    limiting_collection_id: str | None = None
    limiting_collection_name: str | None = None
    is_builtin: bool | None = None
