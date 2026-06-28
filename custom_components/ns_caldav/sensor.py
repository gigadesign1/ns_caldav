"""Sensors for the next NS trip."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import NsCaldavData
from .const import DOMAIN
from .entity import NsTripBaseEntity
from .model import ParsedTrip


@dataclass(frozen=True, kw_only=True)
class NsTripSensorDescription(SensorEntityDescription):
    """Describes an NS trip sensor."""

    value_fn: Callable[[ParsedTrip], StateType]
    attr_fn: Callable[[ParsedTrip], dict[str, Any] | None] | None = None


def _minutes_until(trip: ParsedTrip) -> StateType:
    if trip.actual_departure is None:
        return None
    delta = trip.actual_departure - dt_util.now()
    return max(0, round(delta.total_seconds() / 60))


SENSOR_DESCRIPTIONS: tuple[NsTripSensorDescription, ...] = (
    NsTripSensorDescription(
        key="departure",
        translation_key="departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda t: t.actual_departure,
        attr_fn=lambda t: {
            "planned": t.planned_departure.isoformat()
            if t.planned_departure
            else None,
            "delay_minutes": t.departure_delay_minutes,
        },
    ),
    NsTripSensorDescription(
        key="arrival",
        translation_key="arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda t: t.actual_arrival,
        attr_fn=lambda t: {
            "planned": t.planned_arrival.isoformat() if t.planned_arrival else None,
            "delay_minutes": t.arrival_delay_minutes,
        },
    ),
    NsTripSensorDescription(
        key="departure_station",
        translation_key="departure_station",
        icon="mdi:train",
        value_fn=lambda t: t.departure_station.name,
        attr_fn=lambda t: t.departure_station.as_attributes(),
    ),
    NsTripSensorDescription(
        key="arrival_station",
        translation_key="arrival_station",
        icon="mdi:train",
        value_fn=lambda t: t.arrival_station.name,
        attr_fn=lambda t: t.arrival_station.as_attributes(),
    ),
    NsTripSensorDescription(
        key="departure_track",
        translation_key="departure_track",
        icon="mdi:sign-direction",
        value_fn=lambda t: t.departure_station.track,
    ),
    NsTripSensorDescription(
        key="departure_delay",
        translation_key="departure_delay",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-alert-outline",
        value_fn=lambda t: t.departure_delay_minutes,
    ),
    NsTripSensorDescription(
        key="arrival_delay",
        translation_key="arrival_delay",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-alert-outline",
        value_fn=lambda t: t.arrival_delay_minutes,
    ),
    NsTripSensorDescription(
        key="duration",
        translation_key="duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timeline-clock-outline",
        value_fn=lambda t: t.duration_minutes,
    ),
    NsTripSensorDescription(
        key="transfers",
        translation_key="transfers",
        icon="mdi:transit-transfer",
        value_fn=lambda t: t.transfers,
    ),
    NsTripSensorDescription(
        key="status",
        translation_key="status",
        icon="mdi:information-outline",
        value_fn=lambda t: t.status,
    ),
    NsTripSensorDescription(
        key="crowd_forecast",
        translation_key="crowd_forecast",
        icon="mdi:account-group",
        value_fn=lambda t: t.crowd_forecast,
    ),
    NsTripSensorDescription(
        key="departure_in",
        translation_key="departure_in",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:clock-start",
        value_fn=_minutes_until,
    ),
    NsTripSensorDescription(
        key="price",
        translation_key="price",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda t: t.total_price_eur,
        attr_fn=lambda t: {
            "price_eur": t.price_eur,
            "supplement_eur": t.supplement_eur,
            "total_price_eur": t.total_price_eur,
        },
    ),
    NsTripSensorDescription(
        key="summary",
        translation_key="summary",
        icon="mdi:train-variant",
        value_fn=lambda t: f"{t.origin_name} -> {t.destination_name}",
        attr_fn=lambda t: {
            "planned_departure": t.planned_departure.isoformat()
            if t.planned_departure
            else None,
            "actual_departure": t.actual_departure.isoformat()
            if t.actual_departure
            else None,
            "planned_arrival": t.planned_arrival.isoformat()
            if t.planned_arrival
            else None,
            "actual_arrival": t.actual_arrival.isoformat()
            if t.actual_arrival
            else None,
            "departure_delay_minutes": t.departure_delay_minutes,
            "arrival_delay_minutes": t.arrival_delay_minutes,
            "duration_minutes": t.duration_minutes,
            "transfers": t.transfers,
            "status": t.status,
            "crowd_forecast": t.crowd_forecast,
            "price_eur": t.price_eur,
            "supplement_eur": t.supplement_eur,
            "total_price_eur": t.total_price_eur,
            "is_delayed": t.is_delayed,
            "is_disrupted": t.is_disrupted,
            "messages": t.messages,
            "share_url": t.share_url,
            "summary_text": t.summary_text,
            "departure_station": t.departure_station.as_attributes(),
            "arrival_station": t.arrival_station.as_attributes(),
            "legs": t.legs,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NS trip sensors."""
    data: NsCaldavData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NsTripSensor(data.trip, entry.entry_id, description)
        for description in SENSOR_DESCRIPTIONS
    )


class NsTripSensor(NsTripBaseEntity, SensorEntity):
    """A single sensor describing an aspect of the next trip."""

    entity_description: NsTripSensorDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: NsTripSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor value from the parsed trip."""
        trip = self.coordinator.data
        if trip is None:
            return None
        return self.entity_description.value_fn(trip)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes if the description provides them."""
        trip = self.coordinator.data
        if trip is None or self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(trip)
