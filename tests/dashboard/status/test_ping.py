"""Unit tests for esphome.dashboard.status.ping module."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from esphome.dashboard.status.ping import _resolve_entry_address


@pytest.mark.asyncio
async def test_resolve_entry_address_standard_dns() -> None:
    """Test that standard entries use the DNS cache resolver."""
    dashboard = Mock()
    entry = Mock()
    entry.mdns_resolve_address = False
    entry.address = "device.local"
    dashboard.dns_cache = Mock()
    dashboard.dns_cache.async_resolve = AsyncMock(return_value=["192.168.1.10"])

    result = await _resolve_entry_address(dashboard, entry, 100.0)

    assert result == ["192.168.1.10"]
    dashboard.dns_cache.async_resolve.assert_called_once_with("device.local", 100.0)


@pytest.mark.asyncio
async def test_resolve_entry_address_mdns_resolve_success() -> None:
    """Test that mdns_resolve_address=True entries use python-zeroconf resolution."""
    dashboard = Mock()
    entry = Mock()
    entry.mdns_resolve_address = True
    entry.name = "thread_device"
    mdns_status = Mock()
    mdns_status.async_resolve_host = AsyncMock(
        return_value=["fd11:22:33:44::1", "2001:db8::1"]
    )
    dashboard.mdns_status = mdns_status

    result = await _resolve_entry_address(dashboard, entry, 100.0)

    assert result == ["fd11:22:33:44::1", "2001:db8::1"]
    mdns_status.async_resolve_host.assert_called_once_with("thread_device")


@pytest.mark.asyncio
async def test_resolve_entry_address_mdns_resolve_no_result() -> None:
    """Test that mdns_resolve_address=True returns Exception when zeroconf fails."""
    dashboard = Mock()
    entry = Mock()
    entry.mdns_resolve_address = True
    entry.name = "thread_device"
    mdns_status = Mock()
    mdns_status.async_resolve_host = AsyncMock(return_value=None)
    dashboard.mdns_status = mdns_status

    result = await _resolve_entry_address(dashboard, entry, 100.0)

    assert isinstance(result, Exception)
    assert "thread_device" in str(result)


@pytest.mark.asyncio
async def test_resolve_entry_address_mdns_resolve_no_mdns_status() -> None:
    """Test fallback to DNS cache when mdns_status is None."""
    dashboard = Mock()
    entry = Mock()
    entry.mdns_resolve_address = True
    entry.address = "thread_device.local"
    entry.name = "thread_device"
    dashboard.mdns_status = None
    dashboard.dns_cache = Mock()
    dashboard.dns_cache.async_resolve = AsyncMock(return_value=["192.168.1.20"])

    result = await _resolve_entry_address(dashboard, entry, 100.0)

    # Should fall back to DNS cache when no mdns_status
    assert result == ["192.168.1.20"]
    dashboard.dns_cache.async_resolve.assert_called_once_with(
        "thread_device.local", 100.0
    )


@pytest.mark.asyncio
async def test_resolve_entry_address_mdns_resolve_empty_list() -> None:
    """Test that an empty address list from zeroconf returns an Exception."""
    dashboard = Mock()
    entry = Mock()
    entry.mdns_resolve_address = True
    entry.name = "thread_device"
    mdns_status = Mock()
    mdns_status.async_resolve_host = AsyncMock(return_value=[])
    dashboard.mdns_status = mdns_status

    result = await _resolve_entry_address(dashboard, entry, 100.0)

    assert isinstance(result, Exception)
