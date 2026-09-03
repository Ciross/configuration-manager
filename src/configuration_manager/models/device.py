"""Device domain model."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Device:
    """An immutable Configuration Manager device."""

    id: int
    name: str | None = None
    client_version: str | None = None
    operating_system: str | None = None
    is_active: bool | None = None
    last_active_time: datetime | None = None
