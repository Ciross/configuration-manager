"""Immutable Configuration Manager user model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    """A discovered Configuration Manager user."""

    id: int
    name: str | None = None
    unique_username: str | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    domain: str | None = None
    sid: str | None = None
    distinguished_name: str | None = None
