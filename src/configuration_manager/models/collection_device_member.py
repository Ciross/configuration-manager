"""Collection-to-Device membership relationship model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectionDeviceMember:
    """One device member returned for a Configuration Manager collection."""

    collection_id: str
    device_id: int
    device_name: str | None = None
