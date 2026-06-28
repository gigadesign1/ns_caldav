"""Shared base entity for NS CalDAV Trip."""

from __future__ import annotations

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TripCoordinator


class NsTripBaseEntity(CoordinatorEntity[TripCoordinator]):
    """Base entity grouping all next-trip entities under one device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TripCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="NS Trip (Next)",
            manufacturer="NS",
            model="Reisinformatie",
        )

    @property
    def available(self) -> bool:
        """Available only when a current trip is loaded."""
        return super().available and self.coordinator.data is not None
