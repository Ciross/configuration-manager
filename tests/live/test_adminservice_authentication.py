"""Opt-in validation against a real Configuration Manager lab."""

# Private boundary usage is deliberate for the low-level metadata probe.
# pyright: reportPrivateUsage=false

import os
import sys
from datetime import datetime

import pytest

from configuration_manager import (
    Collection,
    CollectionType,
    ConfigManager,
    Device,
    DeviceCollectionMembership,
)
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


@pytest.mark.live
def test_public_devices_list() -> None:
    """Validate the typed Device collection boundary."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.devices.list(limit=1)
    assert len(page.items) <= 1
    if page.items:
        device = page.items[0]
        assert isinstance(device, Device)
        assert isinstance(device.id, int) and not isinstance(device.id, bool)
        assert device.name is None or isinstance(device.name, str)
        assert device.client_version is None or isinstance(device.client_version, str)
        assert device.operating_system is None or isinstance(
            device.operating_system, str
        )
        assert device.is_active is None or isinstance(device.is_active, bool)
        assert device.last_active_time is None or (
            isinstance(device.last_active_time, datetime)
            and device.last_active_time.tzinfo is not None
            and device.last_active_time.utcoffset() is not None
        )


@pytest.mark.live
def test_public_devices_get_visible_device() -> None:
    """Validate typed keyed lookup using a visible WMI resource ID."""
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
        device = client.devices.get(resource_id)
    assert isinstance(device, Device)
    assert device.id == resource_id


@pytest.mark.live
def test_public_collections_list() -> None:
    """Validate the typed Collection WMI boundary."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.collections.list(limit=1)
    assert len(page.items) <= 1
    if page.items:
        collection = page.items[0]
        assert isinstance(collection, Collection)
        assert isinstance(collection.id, str) and collection.id.strip()
        assert isinstance(collection.collection_type, CollectionType)
        assert collection.name is None or isinstance(collection.name, str)
        assert collection.member_count is None or (
            isinstance(collection.member_count, int)
            and not isinstance(collection.member_count, bool)
            and collection.member_count >= 0
        )
        assert collection.limiting_collection_id is None or isinstance(
            collection.limiting_collection_id, str
        )
        assert collection.limiting_collection_name is None or isinstance(
            collection.limiting_collection_name, str
        )
        assert collection.is_builtin is None or isinstance(collection.is_builtin, bool)


@pytest.mark.live
def test_public_collections_get_visible_collection() -> None:
    """Validate typed keyed lookup using a visible collection ID."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        page = client.raw.wmi.query("SMS_Collection", select=("CollectionID",), top=1)
        if not page.items:
            pytest.skip("the current identity has no visible collections")
        collection_id = page.items[0]["CollectionID"]
        assert isinstance(collection_id, str) and collection_id.strip()
        collection = client.collections.get(collection_id)
    assert isinstance(collection, Collection)
    assert collection.id == collection_id


@pytest.mark.live
def test_public_device_collection_memberships() -> None:
    """Validate the typed Device-to-Collection relationship."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        devices = client.devices.list(limit=10).items
        if not devices:
            pytest.skip("the current identity has no visible devices")
        for device in devices:
            page = client.devices.collection_memberships(device.id, limit=1)
            if page.items:
                membership = page.items[0]
                break
        else:
            pytest.skip("sampled devices have no visible collection memberships")
    assert isinstance(membership, DeviceCollectionMembership)
    assert membership.device_id == device.id
    assert isinstance(membership.collection_id, str)
    assert membership.collection_id.strip()
    if membership.collection_name is not None:
        assert isinstance(membership.collection_name, str)


@pytest.mark.live
def test_public_device_collection_membership_iterator() -> None:
    """Validate lazy public traversal of the Device membership relationship."""
    if sys.platform != "win32":
        pytest.skip("Integrated Authentication validation requires Windows")
    server = os.environ.get("CONFIGURATION_MANAGER_LIVE_SERVER")
    if not server:
        pytest.skip("CONFIGURATION_MANAGER_LIVE_SERVER is not configured")
    with ConfigManager(server=server) as client:
        devices = client.devices.list(limit=10).items
        if not devices:
            pytest.skip("the current identity has no visible devices")
        for device in devices:
            iterator = client.devices.iter_collection_memberships(device.id)
            item = next(iterator, None)
            if item is not None:
                break
        else:
            pytest.skip("sampled devices have no visible collection memberships")
    assert isinstance(item, DeviceCollectionMembership)
    assert item.device_id == device.id
