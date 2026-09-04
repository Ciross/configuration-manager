"""User-to-Collection relationship model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserCollectionMembership:
    """A collection to which a ConfigMgr user belongs."""

    user_id: int
    collection_id: str
