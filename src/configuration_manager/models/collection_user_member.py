"""Collection-to-User membership relationship model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectionUserMember:
    """One user member returned for a Configuration Manager collection."""

    collection_id: str
    user_id: int
    user_name: str | None = None
