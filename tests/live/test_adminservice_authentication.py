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


@pytest.mark.live
def test_public_wmi_get_visible_system() -> None:
    """Fetch one visible system through the public keyed WMI API."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.raw.wmi.query(
            "SMS_R_System", select=("ResourceId", "Name"), top=1
        )
        if not page.items:
            pytest.skip("the current identity has no visible systems")
        resource_id = page.items[0]["ResourceId"]
        assert isinstance(resource_id, int) and not isinstance(resource_id, bool)
        fetched = client.raw.wmi.get(
            "SMS_R_System", resource_id, select=("ResourceId", "Name")
        )
    assert fetched is not None
    assert fetched["ResourceId"] == resource_id
    assert "Name" in fetched


@pytest.mark.live
def test_public_v1_device_query() -> None:
    """Validate the public versioned Device collection route."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.raw.v1.query("Device", top=1)
    assert len(page.items) <= 1
    if page.items:
        assert bool(page.items[0])


@pytest.mark.live
def test_public_v1_get_visible_device() -> None:
    """Fetch a versioned Device whose resource is visible through WMI."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.raw.wmi.query("SMS_R_System", select=("ResourceId",), top=1)
        if not page.items:
            pytest.skip("the current identity has no visible systems")
        resource_id = page.items[0]["ResourceId"]
        assert isinstance(resource_id, int) and not isinstance(resource_id, bool)
        device = client.raw.v1.get("Device", resource_id)
    assert device is not None
    assert bool(device)
