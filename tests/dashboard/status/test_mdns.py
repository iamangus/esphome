"""Unit tests for esphome.dashboard.status.mdns module."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from zeroconf import AddressResolver, IPVersion

from esphome.dashboard.const import DashboardEvent
from esphome.dashboard.status.mdns import MDNSStatus
from esphome.zeroconf import DiscoveredImport


@pytest_asyncio.fixture
async def mdns_status(mock_dashboard: Mock) -> MDNSStatus:
    """Create an MDNSStatus instance in async context."""
    # We're in an async context so get_running_loop will work
    return MDNSStatus(mock_dashboard)


@pytest.mark.asyncio
async def test_get_cached_addresses_no_zeroconf(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses when no zeroconf instance is available."""
    mdns_status.aiozc = None
    result = mdns_status.get_cached_addresses("device.local")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_addresses_not_in_cache(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses when address is not in cache."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = False
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device.local")
        assert result is None
        mock_info.load_from_cache.assert_called_once_with(mdns_status.aiozc.zeroconf)


@pytest.mark.asyncio
async def test_get_cached_addresses_found_in_cache(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses when address is found in cache."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = ["192.168.1.10", "fe80::1"]
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device.local")
        assert result == ["192.168.1.10", "fe80::1"]
        mock_info.load_from_cache.assert_called_once_with(mdns_status.aiozc.zeroconf)
        mock_info.parsed_scoped_addresses.assert_called_once_with(IPVersion.All)


@pytest.mark.asyncio
async def test_get_cached_addresses_with_trailing_dot(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses with hostname having trailing dot."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = ["192.168.1.10"]
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device.local.")
        assert result == ["192.168.1.10"]
        # Should normalize to device.local. for zeroconf
        mock_resolver.assert_called_once_with("device.local.")


@pytest.mark.asyncio
async def test_get_cached_addresses_uppercase_hostname(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses with uppercase hostname."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = ["192.168.1.10"]
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("DEVICE.LOCAL")
        assert result == ["192.168.1.10"]
        # Should normalize to device.local. for zeroconf
        mock_resolver.assert_called_once_with("device.local.")


@pytest.mark.asyncio
async def test_get_cached_addresses_simple_hostname(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses with simple hostname (no domain)."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = ["192.168.1.10"]
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device")
        assert result == ["192.168.1.10"]
        # Should append .local. for zeroconf
        mock_resolver.assert_called_once_with("device.local.")


@pytest.mark.asyncio
async def test_get_cached_addresses_ipv6_only(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses returning only IPv6 addresses."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = ["fe80::1", "2001:db8::1"]
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device.local")
        assert result == ["fe80::1", "2001:db8::1"]


@pytest.mark.asyncio
async def test_get_cached_addresses_empty_list(mdns_status: MDNSStatus) -> None:
    """Test get_cached_addresses returning empty list from cache."""
    mdns_status.aiozc = Mock()
    mdns_status.aiozc.zeroconf = Mock()

    with patch("esphome.dashboard.status.mdns.AddressResolver") as mock_resolver:
        mock_info = Mock(spec=AddressResolver)
        mock_info.load_from_cache.return_value = True
        mock_info.parsed_scoped_addresses.return_value = []
        mock_resolver.return_value = mock_info

        result = mdns_status.get_cached_addresses("device.local")
        assert result == []


@pytest.mark.asyncio
async def test_async_setup_success(mock_dashboard: Mock) -> None:
    """Test successful async_setup."""
    mdns_status = MDNSStatus(mock_dashboard)
    with patch("esphome.dashboard.status.mdns.AsyncEsphomeZeroconf") as mock_zc:
        mock_zc.return_value = Mock()
        result = mdns_status.async_setup()
        assert result is True
        assert mdns_status.aiozc is not None


@pytest.mark.asyncio
async def test_async_setup_failure(mock_dashboard: Mock) -> None:
    """Test async_setup with OSError."""
    mdns_status = MDNSStatus(mock_dashboard)
    with patch("esphome.dashboard.status.mdns.AsyncEsphomeZeroconf") as mock_zc:
        mock_zc.side_effect = OSError("Network error")
        result = mdns_status.async_setup()
        assert result is False
        assert mdns_status.aiozc is None


@pytest.mark.asyncio
async def test_on_import_update_device_added(mdns_status: MDNSStatus) -> None:
    """Test _on_import_update when a device is added."""
    # Create a DiscoveredImport object
    discovered = DiscoveredImport(
        device_name="test_device",
        friendly_name="Test Device",
        package_import_url="https://example.com/package",
        project_name="test_project",
        project_version="1.0.0",
        network="wifi",
    )

    # Call _on_import_update with a device
    mdns_status._on_import_update("test_device", discovered)

    # Should fire IMPORTABLE_DEVICE_ADDED event
    mock_dashboard = mdns_status.dashboard
    mock_dashboard.bus.async_fire.assert_called_once()
    call_args = mock_dashboard.bus.async_fire.call_args
    assert call_args[0][0] == DashboardEvent.IMPORTABLE_DEVICE_ADDED
    assert "device" in call_args[0][1]
    device_data = call_args[0][1]["device"]
    assert device_data["name"] == "test_device"
    assert device_data["friendly_name"] == "Test Device"
    assert device_data["project_name"] == "test_project"
    assert device_data["ignored"] is False


@pytest.mark.asyncio
async def test_on_import_update_device_ignored(mdns_status: MDNSStatus) -> None:
    """Test _on_import_update when a device is ignored."""
    # Add device to ignored list
    mdns_status.dashboard.ignored_devices.add("ignored_device")

    # Create a DiscoveredImport object for ignored device
    discovered = DiscoveredImport(
        device_name="ignored_device",
        friendly_name="Ignored Device",
        package_import_url="https://example.com/package",
        project_name="test_project",
        project_version="1.0.0",
        network="ethernet",
    )

    # Call _on_import_update with an ignored device
    mdns_status._on_import_update("ignored_device", discovered)

    # Should fire IMPORTABLE_DEVICE_ADDED event with ignored=True
    mock_dashboard = mdns_status.dashboard
    mock_dashboard.bus.async_fire.assert_called_once()
    call_args = mock_dashboard.bus.async_fire.call_args
    assert call_args[0][0] == DashboardEvent.IMPORTABLE_DEVICE_ADDED
    device_data = call_args[0][1]["device"]
    assert device_data["name"] == "ignored_device"
    assert device_data["ignored"] is True


@pytest.mark.asyncio
async def test_on_import_update_device_removed(mdns_status: MDNSStatus) -> None:
    """Test _on_import_update when a device is removed."""
    # Call _on_import_update with None (device removed)
    mdns_status._on_import_update("removed_device", None)

    # Should fire IMPORTABLE_DEVICE_REMOVED event
    mdns_status.dashboard.bus.async_fire.assert_called_once_with(
        DashboardEvent.IMPORTABLE_DEVICE_REMOVED, {"name": "removed_device"}
    )


def _make_entry(
    *,
    name: str,
    no_mdns: bool = False,
    loaded_integrations: set[str] | None = None,
    mdns_resolve_address: bool = False,
) -> Mock:
    """Helper to create a mock DashboardEntry."""
    entry = Mock()
    entry.name = name
    entry.no_mdns = no_mdns
    entry.loaded_integrations = loaded_integrations or set()
    entry.mdns_resolve_address = mdns_resolve_address
    return entry


@pytest.mark.asyncio
async def test_async_refresh_hosts_mdns_resolve_address_with_api_is_polled(
    mdns_status: MDNSStatus,
) -> None:
    """Verify that mdns_resolve_address=True entries with API are actively polled.

    Previously, devices with API were skipped from poll_names and relied on the
    DashboardStatus browser callback. For OpenThread devices whose
    _esphomelib._tcp.local. service may not be visible to the dashboard's
    zeroconf browser via the Thread Border Router, this meant their state was
    never updated and their addresses were never cached. The fix adds
    mdns_resolve_address=True entries to poll_names regardless of API presence.
    """
    # OpenThread device: has API and mdns_resolve_address=True
    ot_entry = _make_entry(
        name="thread-device",
        loaded_integrations={"api", "openthread"},
        mdns_resolve_address=True,
    )
    mdns_status.dashboard.entries.async_all.return_value = [ot_entry]
    mdns_status.aiozc = AsyncMock()
    mdns_status.aiozc.async_resolve_host = AsyncMock(
        return_value=["fd11:22:33:44::1"]
    )

    await mdns_status.async_refresh_hosts()

    # Should have been polled via async_resolve_host (not skipped for having API)
    mdns_status.aiozc.async_resolve_host.assert_called_once_with("thread-device")


@pytest.mark.asyncio
async def test_async_refresh_hosts_mdns_resolve_address_sets_online_when_resolved(
    mdns_status: MDNSStatus,
) -> None:
    """Verify that mdns_resolve_address=True device becomes ONLINE when address resolves."""
    from esphome.dashboard.entries import EntryStateSource, ReachableState

    ot_entry = _make_entry(
        name="thread-device",
        loaded_integrations={"api", "openthread"},
        mdns_resolve_address=True,
    )
    mdns_status.dashboard.entries.async_all.return_value = [ot_entry]
    mdns_status.aiozc = AsyncMock()
    mdns_status.aiozc.async_resolve_host = AsyncMock(
        return_value=["fd11:22:33:44::1"]
    )

    await mdns_status.async_refresh_hosts()

    # State should be set to ONLINE from MDNS source
    mdns_status.dashboard.entries.async_set_state.assert_called_once()
    call_args = mdns_status.dashboard.entries.async_set_state.call_args
    state = call_args[0][1]
    assert state.reachable == ReachableState.ONLINE
    assert state.source == EntryStateSource.MDNS


@pytest.mark.asyncio
async def test_async_refresh_hosts_mdns_resolve_address_sets_offline_when_unresolved(
    mdns_status: MDNSStatus,
) -> None:
    """Verify that mdns_resolve_address=True device becomes OFFLINE when address fails."""
    from esphome.dashboard.entries import EntryStateSource, ReachableState

    ot_entry = _make_entry(
        name="thread-device",
        loaded_integrations={"api", "openthread"},
        mdns_resolve_address=True,
    )
    # Set current state to UNKNOWN so the offline state can be written
    from esphome.dashboard.entries import UNKNOWN_STATE
    ot_entry.state = UNKNOWN_STATE
    mdns_status.dashboard.entries.async_all.return_value = [ot_entry]
    mdns_status.aiozc = AsyncMock()
    # Resolution fails: returns None
    mdns_status.aiozc.async_resolve_host = AsyncMock(return_value=None)

    await mdns_status.async_refresh_hosts()

    # Should call async_set_state_if_source (since result is False)
    mdns_status.dashboard.entries.async_set_state_if_source.assert_called_once()
    call_args = mdns_status.dashboard.entries.async_set_state_if_source.call_args
    state = call_args[0][1]
    assert state.reachable == ReachableState.OFFLINE
    assert state.source == EntryStateSource.MDNS


@pytest.mark.asyncio
async def test_async_refresh_hosts_normal_api_device_uses_host_mdns_state(
    mdns_status: MDNSStatus,
) -> None:
    """Verify that normal devices with API still use host_mdns_state (not poll_names)."""
    from esphome.dashboard.entries import EntryStateSource, ReachableState

    # Normal WiFi device with API (not mdns_resolve_address)
    wifi_entry = _make_entry(
        name="wifi-device",
        loaded_integrations={"api", "wifi"},
        mdns_resolve_address=False,
    )
    mdns_status.dashboard.entries.async_all.return_value = [wifi_entry]
    mdns_status.aiozc = AsyncMock()
    mdns_status.aiozc.async_resolve_host = AsyncMock(return_value=["192.168.1.10"])
    # Simulate browser having seen this device
    mdns_status.host_mdns_state["wifi-device"] = True

    await mdns_status.async_refresh_hosts()

    # Normal API device should NOT be polled via async_resolve_host
    mdns_status.aiozc.async_resolve_host.assert_not_called()
    # Should have been updated from host_mdns_state
    mdns_status.dashboard.entries.async_set_state.assert_called_once()
    call_args = mdns_status.dashboard.entries.async_set_state.call_args
    state = call_args[0][1]
    assert state.reachable == ReachableState.ONLINE
    assert state.source == EntryStateSource.MDNS


@pytest.mark.asyncio
async def test_async_refresh_hosts_no_api_device_still_polled(
    mdns_status: MDNSStatus,
) -> None:
    """Verify that devices without API are still polled via poll_names."""
    no_api_entry = _make_entry(
        name="no-api-device",
        loaded_integrations={"mqtt"},
        mdns_resolve_address=False,
    )
    mdns_status.dashboard.entries.async_all.return_value = [no_api_entry]
    mdns_status.aiozc = AsyncMock()
    mdns_status.aiozc.async_resolve_host = AsyncMock(return_value=["192.168.1.20"])

    await mdns_status.async_refresh_hosts()

    # No-API device should still be polled via async_resolve_host
    mdns_status.aiozc.async_resolve_host.assert_called_once_with("no-api-device")
