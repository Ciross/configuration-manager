"""Device-to-Collection relationship model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceCollectionMembership:
    """A collection to which a ConfigMgr device belongs."""

    device_id: int
    collection_id: str
    collection_name: str | None = None
