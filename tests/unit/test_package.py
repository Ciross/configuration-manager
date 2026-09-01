"""Tests for the package scaffold."""

import configuration_manager


def test_package_is_importable() -> None:
    """The installed source package can be imported."""
    assert configuration_manager.__all__ == ()
