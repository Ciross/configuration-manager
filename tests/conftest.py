"""Shared pytest configuration and safety controls."""

# Pyright cannot discover pytest's dynamically registered hook and node types.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false

from collections.abc import Generator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the explicit opt-in switch for tests that target a live lab."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that require a live Configuration Manager lab",
    )


@pytest.fixture(autouse=True)
def _require_live_test_opt_in(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Skip live tests unless the developer supplied ``--run-live``."""
    if request.node.get_closest_marker("live") and not request.config.getoption(
        "--run-live"
    ):
        pytest.skip("live tests require the --run-live option")
    yield
