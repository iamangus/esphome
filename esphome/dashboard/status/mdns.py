from __future__ import annotations

import asyncio
import logging
import re
import typing

from zeroconf import AddressResolver, IPVersion

from esphome.address_cache import normalize_hostname
from esphome.zeroconf import (
    ESPHOME_SERVICE_TYPE,
    AsyncEsphomeZeroconf,
    DashboardBrowser,
    DashboardImportDiscovery,
    DashboardStatus,
    DiscoveredImport,
)

from ..const import SENTINEL, DashboardEvent
from ..entries import DashboardEntry, EntryStateSource, bool_to_entry_state
from ..models import build_importable_device_dict

if typing.TYPE_CHECKING:
    from ..core import ESPHomeDashboard

_LOGGER = logging.getLogger(__name__)

# Matches a hostname that ends with a 6-hex-character MAC suffix, e.g. "device-a1b2c3".
# ESPHome appends the last 3 bytes of the MAC address when name_add_mac_suffix is set.
_MAC_SUFFIX_RE = re.compile(r"^(.+)-[0-9a-f]{6}$", re.IGNORECASE)


class MDNSStatus:
    """Class that updates the mdns status."""

    def __init__(self, dashboard: ESPHomeDashboard) -> None:
        """Initialize the MDNSStatus class."""
        super().__init__()
        self.aiozc: AsyncEsphomeZeroconf | None = None
        # This is the current mdns state for each host (True, False, None)
        self.host_mdns_state: dict[str, bool | None] = {}
        # Maps base device name -> discovered MAC-suffixed hostname.
        # Populated when the mDNS browser finds a service whose instance name
        # matches the pattern "<base>-<6 hex chars>" and the base name corresponds
        # to a known dashboard entry (e.g. name_add_mac_suffix: true devices).
        self.mac_suffix_name_map: dict[str, str] = {}
        self._loop = asyncio.get_running_loop()
        self.dashboard = dashboard

    def async_setup(self) -> bool:
        """Set up the MDNSStatus class."""
        try:
            self.aiozc = AsyncEsphomeZeroconf()
        except OSError as e:
            _LOGGER.warning(
                "Failed to initialize zeroconf, will fallback to ping: %s", e
            )
            return False
        return True

    async def async_resolve_host(self, host_name: str) -> list[str] | None:
        """Resolve a host name to an address in a thread-safe manner.

        When a MAC-suffixed variant of the hostname is known (from the mDNS
        browser discovering a ``name_add_mac_suffix`` device), that name is used
        directly to avoid a slow multicast timeout against a name that does not exist.
        """
        if aiozc := self.aiozc:
            # Use the MAC-suffixed name if one has been discovered for this base name.
            # This handles devices with name_add_mac_suffix: true, where the device
            # registers as e.g. "device-aabbcc.local." instead of "device.local.".
            effective_name = self.mac_suffix_name_map.get(host_name, host_name)
            return await aiozc.async_resolve_host(effective_name)
        return None

    def get_cached_addresses(self, host_name: str) -> list[str] | None:
        """Get cached addresses for a host without triggering resolution.

        Returns None if not in cache or no zeroconf available.
        Falls back to the MAC-suffixed variant (from ``mac_suffix_name_map``) when
        the base name is not cached, so OTA pre-resolution works for devices with
        ``name_add_mac_suffix: true``.
        """
        if not self.aiozc:
            _LOGGER.debug("No zeroconf instance available for %s", host_name)
            return None

        # Normalize hostname and get the base name
        normalized = normalize_hostname(host_name)
        base_name = normalized.partition(".")[0]

        # Try to load from zeroconf cache without triggering resolution
        resolver_name = f"{base_name}.local."
        info = AddressResolver(resolver_name)
        # Let zeroconf use its own current time for cache checking
        if info.load_from_cache(self.aiozc.zeroconf):
            addresses = info.parsed_scoped_addresses(IPVersion.All)
            _LOGGER.debug("Found %s in zeroconf cache: %s", resolver_name, addresses)
            return addresses

        # Fall back to the MAC-suffixed variant if one is known.
        # This handles name_add_mac_suffix: true devices whose actual mDNS hostname
        # is e.g. "device-aabbcc.local." rather than "device.local.".
        if mac_name := self.mac_suffix_name_map.get(base_name):
            mac_resolver_name = f"{mac_name}.local."
            mac_info = AddressResolver(mac_resolver_name)
            if mac_info.load_from_cache(self.aiozc.zeroconf):
                addresses = mac_info.parsed_scoped_addresses(IPVersion.All)
                _LOGGER.debug(
                    "Found %s in zeroconf cache via MAC-suffix fallback: %s",
                    mac_resolver_name,
                    addresses,
                )
                return addresses

        _LOGGER.debug("Not found in zeroconf cache: %s", resolver_name)
        return None

    def _on_import_update(self, name: str, discovered: DiscoveredImport | None) -> None:
        """Handle importable device updates."""
        if discovered is None:
            # Device removed
            self.dashboard.bus.async_fire(
                DashboardEvent.IMPORTABLE_DEVICE_REMOVED, {"name": name}
            )
        else:
            # Device added
            self.dashboard.bus.async_fire(
                DashboardEvent.IMPORTABLE_DEVICE_ADDED,
                {"device": build_importable_device_dict(self.dashboard, discovered)},
            )

    async def async_refresh_hosts(self) -> None:
        """Refresh the hosts to track."""
        dashboard = self.dashboard
        host_mdns_state = self.host_mdns_state
        entries = dashboard.entries
        poll_names: dict[str, set[DashboardEntry]] = {}
        for entry in entries.async_all():
            if entry.no_mdns:
                continue
            # If we just adopted/imported this host, we likely
            # already have a state for it, so we should make sure
            # to set it so the dashboard shows it as online
            if (
                entry.loaded_integrations and "api" not in entry.loaded_integrations
            ) or entry.mdns_resolve_address:
                # No api available so we have to poll since
                # the device won't respond to a request to ._esphomelib._tcp.local.
                # Also poll devices with mdns_resolve_address=True (e.g. OpenThread)
                # since their _esphomelib._tcp.local. service may not be visible
                # to the dashboard's zeroconf browser via the Thread Border Router.
                # Active polling ensures addresses are cached in zeroconf and the
                # device status is kept up to date.
                #
                # Use the MAC-suffixed name if one has been discovered, so that
                # devices with name_add_mac_suffix: true resolve correctly.
                poll_name = self.mac_suffix_name_map.get(entry.name, entry.name)
                poll_names.setdefault(poll_name, set()).add(entry)
            elif (online := host_mdns_state.get(entry.name, SENTINEL)) != SENTINEL:
                self._async_set_state(entry, online)
        if poll_names and self.aiozc:
            results = await asyncio.gather(
                *(self.aiozc.async_resolve_host(name) for name in poll_names)
            )
            for name, address_list in zip(poll_names, results):
                result = bool(address_list)
                host_mdns_state[name] = result
                for entry in poll_names[name]:
                    self._async_set_state(entry, result)

    def _async_set_state(self, entry: DashboardEntry, result: bool | None) -> None:
        """Set the state of an entry."""
        state = bool_to_entry_state(result, EntryStateSource.MDNS)
        if result:
            # If we can reach it via mDNS, we always set it online
            # since its the fastest source if its working
            self.dashboard.entries.async_set_state(entry, state)
        else:
            # However if we can't reach it via mDNS
            # we only set it to offline if the state is unknown
            # or from mDNS
            self.dashboard.entries.async_set_state_if_source(entry, state)

    async def async_run(self) -> None:
        """Run the mdns status."""
        dashboard = self.dashboard
        entries = dashboard.entries
        host_mdns_state = self.host_mdns_state

        def on_update(dat: dict[str, bool | None]) -> None:
            """Update the entry state."""
            for name, result in dat.items():
                host_mdns_state[name] = result
                if matching_entries := entries.get_by_name(name):
                    for entry in matching_entries:
                        self._async_set_state(entry, result)
                elif mac_match := _MAC_SUFFIX_RE.match(name):
                    # No direct entry found but the name looks like a MAC-suffixed
                    # variant (e.g. "device-a1b2c3" from name_add_mac_suffix: true).
                    # Map it to its base name so that mDNS resolution and cache
                    # lookups use the correct hostname for all wireless operations
                    # (status, OTA, API, logs, etc.).
                    base_name = mac_match.group(1)
                    if base_entries := entries.get_by_name(base_name):
                        self.mac_suffix_name_map[base_name] = name
                        for entry in base_entries:
                            self._async_set_state(entry, result)

        stat = DashboardStatus(on_update)

        imports = DashboardImportDiscovery(self._on_import_update)
        dashboard.import_result = imports.import_state

        browser = DashboardBrowser(
            self.aiozc.zeroconf,
            ESPHOME_SERVICE_TYPE,
            [stat.browser_callback, imports.browser_callback],
        )

        ping_request = dashboard.ping_request
        while not dashboard.stop_event.is_set():
            await self.async_refresh_hosts()
            await ping_request.wait()
            ping_request.clear()

        await browser.async_cancel()
        await self.aiozc.async_close()
        self.aiozc = None
