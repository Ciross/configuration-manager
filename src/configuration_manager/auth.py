"""AdminService-specific authentication type boundary."""

from typing import Protocol


class AdminServiceAuth(Protocol):
    """Marker for a future AdminService authentication strategy.

    HTTP adapter behavior is intentionally absent until an HTTP stack is selected
    and validated. Authentication is not part of the generic provider transport.
    """
