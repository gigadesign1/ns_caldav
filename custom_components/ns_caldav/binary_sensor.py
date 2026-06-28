"""Binary sensors for the next NS trip (leave-soon, delayed, disruption)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from . import NsCaldavData
from .const import (
    CONF_DELAY_THRESHOLD_MINUTES,
    CONF_NOTIFY_LEAD_MINUTES,
    DEFAULT_DELAY_THRESHOLD_MINUTES,
    DEFAULT_NOTIFY_LEAD_MINUTES,
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
    lead = entry.options.get(CONF_NOTIFY_LEAD_MINUTES, DEFAULT_NOTIFY_LEAD_MINUTES)
    threshold = entry.options.get(
        CONF_DELAY_THRESHOLD_MINUTES, DEFAULT_DELAY_THRESHOLD_MINUTES
    )
    async_add_entities(
        [
            NsLeaveSoonBinarySensor(data.trip, entry.entry_id, lead),
            NsDelayedBinarySensor(data.trip, entry.entry_id, threshold),
            NsDisruptionBinarySensor(data.trip, entry.entry_id),
        ]
    )


class NsLeaveSoonBinarySensor(NsTripBaseEntity, BinarySensorEntity):
    """On from (actual departure - lead) until actual departure.

    Flips precisely using a scheduled point-in-time timer so notifications fire
    on time, and reschedules whenever the coordinator reports a new departure
    (e.g. because of a delay).
    """

    _attr_translation_key = "leave_soon"
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(
        self, coordinator: TripCoordinator, entry_id: str, lead_minutes: int
    ) -> None:
        super().__init__(coordinator, entry_id, "leave_soon")
        self._lead = timedelta(minutes=lead_minutes)
        self._unsub_timer = None

    def _window(self) -> tuple[datetime, datetime] | None:
        trip = self.coordinator.data
        if trip is None or trip.actual_departure is None:
            return None
        return trip.actual_departure - self._lead, trip.actual_departure

    @property
    def is_on(self) -> bool:
        """True when within the lead window before departure."""
        window = self._window()
        if window is None:
            return False
        start, end = window
        return start <= dt_util.now() <= end

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _schedule(self) -> None:
        self._cancel_timer()
        window = self._window()
        if window is None:
            return
        now = dt_util.now()
        start, end = window
        next_point: datetime | None = None
        if now < start:
            next_point = start
        elif now < end:
            next_point = end
        if next_point is not None:
            self._unsub_timer = async_track_point_in_time(
                self.hass, self._handle_timer, next_point
            )

    @callback
    def _handle_timer(self, _now: datetime) -> None:
        self.async_write_ha_state()
        self._schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Schedule the initial flip when added."""
        await super().async_added_to_hass()
        self._schedule()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending timer on removal."""
        self._cancel_timer()
        await super().async_will_remove_from_hass()


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
