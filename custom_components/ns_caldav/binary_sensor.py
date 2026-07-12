"""Binary sensors for the next NS trip (delayed, disruption)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NsCaldavData
from .const import (
    CONF_DELAY_THRESHOLD_MINUTES,
    DEFAULT_DELAY_THRESHOLD_MINUTES,
    DOMAIN,
)
from .coordinator import TripCoordinator
from .entity import NsTripBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NS trip binary sensors."""
    data: NsCaldavData = hass.data[DOMAIN][entry.entry_id]
    threshold = entry.options.get(
        CONF_DELAY_THRESHOLD_MINUTES, DEFAULT_DELAY_THRESHOLD_MINUTES
    )
    async_add_entities(
        [
            NsDelayedBinarySensor(data.trip, entry.entry_id, threshold),
            NsDisruptionBinarySensor(data.trip, entry.entry_id),
        ]
    )


class NsDelayedBinarySensor(NsTripBaseEntity, BinarySensorEntity):
    """On when departure or arrival delay meets the configured threshold."""

    _attr_translation_key = "delayed"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: TripCoordinator, entry_id: str, threshold_minutes: int
    ) -> None:
        super().__init__(coordinator, entry_id, "delayed")
        self._threshold = max(1, threshold_minutes)

    @property
    def is_on(self) -> bool:
        """True when the trip is delayed beyond the threshold."""
        trip = self.coordinator.data
        if trip is None:
            return False
        worst = max(trip.departure_delay_minutes, trip.arrival_delay_minutes)
        return worst >= self._threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the delay magnitudes."""
        trip = self.coordinator.data
        if trip is None:
            return None
        return {
            "departure_delay_minutes": trip.departure_delay_minutes,
            "arrival_delay_minutes": trip.arrival_delay_minutes,
        }


class NsDisruptionBinarySensor(NsTripBaseEntity, BinarySensorEntity):
    """On when the trip is cancelled/disrupted or has messages."""

    _attr_translation_key = "disruption"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: TripCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "disruption")

    @property
    def is_on(self) -> bool:
        """True when the trip status is abnormal or messaged."""
        trip = self.coordinator.data
        return bool(trip and trip.is_disrupted)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose status and any disruption messages."""
        trip = self.coordinator.data
        if trip is None:
            return None
        return {"status": trip.status, "messages": trip.messages}
