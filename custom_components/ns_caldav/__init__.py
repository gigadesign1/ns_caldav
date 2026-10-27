"""The NS CalDAV Trip integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    CARD_FILENAME,
    CARD_REGISTERED,
    CARD_URL_PATH,
    CONF_SUBSCRIPTION_KEY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import DiscoveryCoordinator, TripCoordinator
from .ns_api import NsApiClient
from .storage import TripStore

_LOGGER = logging.getLogger(__name__)


@dataclass
class NsCaldavData:
    """Runtime objects shared across the integration's platforms."""

    store: TripStore
    discovery: DiscoveryCoordinator
    trip: TripCoordinator


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and load it as a frontend module (once).

    Failures here must never break entity setup, so everything is best-effort
    and logged. Storage-mode dashboards load the card as a Lovelace resource;
    YAML-mode dashboards fall back to ``add_extra_js_url``.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(CARD_REGISTERED):
        return

    card_path = Path(__file__).parent / "frontend" / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.error("NS perronbord card file is missing at %s", card_path)
        return

    try:
        await _async_register_static_path(hass, CARD_URL_PATH, str(card_path))
    except Exception:  # noqa: BLE001 - best-effort; do not break setup
        _LOGGER.exception("Failed to serve the NS perronbord card")
        return

    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version or "0"
    except Exception:  # noqa: BLE001 - version is best-effort cache busting only
        version = "0"

    card_url = f"{CARD_URL_PATH}?v={version}"
    try:
        if await _async_register_lovelace_resource(hass, card_url):
            _LOGGER.info("Registered NS perronbord card resource at %s", card_url)
        else:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, card_url)
            _LOGGER.warning(
                "Lovelace resources are not in storage mode; loaded the NS "
                "perronbord card through the frontend fallback. For reliable "
                "loading in YAML mode, add %s as a JavaScript module resource",
                CARD_URL_PATH,
            )
    except Exception:  # noqa: BLE001 - best-effort; do not break setup
        _LOGGER.exception("Failed to load the NS perronbord card module")
    finally:
        # The static route cannot be registered twice. Mark this attempt done
        # even if optional Lovelace resource registration failed.
        domain_data[CARD_REGISTERED] = True


async def _async_register_lovelace_resource(
    hass: HomeAssistant, card_url: str
) -> bool:
    """Create or update the card's storage-mode Lovelace resource."""
    lovelace_data: Any = hass.data.get("lovelace")
    if lovelace_data is None:
        return False

    resources = getattr(lovelace_data, "resources", None)
    if resources is None and isinstance(lovelace_data, dict):
        # Home Assistant < 2025.2 stored Lovelace data in a dictionary.
        resources = lovelace_data.get("resources")

    if resources is None or getattr(resources, "store", None) is None:
        return False

    if not resources.loaded:
        await resources.async_load()

    for item in resources.async_items():
        if item["url"].split("?", 1)[0] != CARD_URL_PATH:
            continue
        if item["url"] != card_url:
            await resources.async_update_item(item["id"], {"url": card_url})
        return True

    await resources.async_create_item({"res_type": "module", "url": card_url})
    return True


async def _async_register_static_path(hass: HomeAssistant, url: str, path: str) -> None:
    """Register a static file path, supporting old and new HA APIs."""
    register_async = getattr(hass.http, "async_register_static_paths", None)
    if register_async is not None:
        from homeassistant.components.http import StaticPathConfig

        await register_async([StaticPathConfig(url, path, False)])
        return
    # Fallback for Home Assistant < 2024.7.
    hass.http.register_static_path(url, path, cache_headers=False)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-wide resources."""
    await _async_register_frontend_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NS CalDAV Trip from a config entry."""
    await _async_register_frontend_card(hass)

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
