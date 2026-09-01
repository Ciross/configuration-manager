"""Tests for the live-test directory safety boundary."""

from pathlib import Path

from conftest import is_live_test_path


def test_live_test_directory_is_recognized() -> None:
    """All files nested under the live-test directory are treated as live."""
    live_test = Path(__file__).parents[1] / "live" / "nested" / "test_example.py"

    assert is_live_test_path(live_test)


def test_non_live_test_directory_is_not_recognized() -> None:
    """Tests elsewhere in the suite are not treated as live by location."""
    unit_test = Path(__file__)

    assert not is_live_test_path(unit_test)
