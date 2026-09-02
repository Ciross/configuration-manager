"""Opt-in validation against a real Configuration Manager lab."""

# Private boundary usage is deliberate for the low-level metadata probe.
# pyright: reportPrivateUsage=false

import os
import sys

import pytest

from configuration_manager import ConfigManager
from configuration_manager.adminservice import (
    AdminService,
    windows_integrated_authentication,
)
from configuration_manager.transport import AdminServiceSurface


@pytest.mark.live
def test_windows_integrated_authentication_and_metadata() -> None:
    """Validate system TLS trust, current credentials, and read-only metadata."""
    if sys.platform != "win32":
        pytest.skip("initial Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")

    with AdminService(server, auth=windows_integrated_authentication()) as adminservice:
        metadata = adminservice.get_text(AdminServiceSurface.V1, "$metadata")
    assert "edmx" in metadata.lower()


@pytest.mark.live
def test_public_wmi_query() -> None:
    """Validate the built-in read-only WMI query vertical slice."""
    if sys.platform != "win32":
        pytest.skip("initial Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.raw.wmi.query(
            "SMS_R_System", select=("ResourceId", "Name"), top=1
        )
    assert len(page.items) <= 1
    for record in page.items:
        assert "ResourceId" in record
        assert "Name" in record
