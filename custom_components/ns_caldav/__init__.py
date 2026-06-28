"""The NS CalDAV Trip integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SUBSCRIPTION_KEY, DOMAIN, PLATFORMS
from .coordinator import DiscoveryCoordinator, TripCoordinator
from .ns_api import NsApiClient
from .storage import TripStore


@dataclass
class NsCaldavData:
    """Runtime objects shared across the integration's platforms."""

    store: TripStore
    discovery: DiscoveryCoordinator
    trip: TripCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NS CalDAV Trip from a config entry."""
    store = TripStore(hass, entry.entry_id)
    await store.async_load()

    client = NsApiClient(hass, entry.data[CONF_SUBSCRIPTION_KEY])
    discovery = DiscoveryCoordinator(hass, entry, store, client)
    trip = TripCoordinator(hass, entry, store, client)
    discovery.trip_coordinator = trip

    # Populate the store from the calendar first, then resolve the next trip.
    await discovery.async_config_entry_first_refresh()
    await trip.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = NsCaldavData(
        store=store, discovery=discovery, trip=trip
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the persisted trip store when the entry is deleted."""
    store = TripStore(hass, entry.entry_id)
    await store.async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
