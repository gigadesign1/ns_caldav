"""Persistent storage of resolved NS trips.

Discovery writes resolved trips here; the trip coordinator reads them. Keeping
this in a small JSON-backed :class:`Store` decouples the (slow, hourly) calendar
scan from the (fast, adaptive) trip polling and survives restarts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


@dataclass
class StoredTrip:
    """A single trip discovered in the calendar and resolved to a ctxRecon."""

    token: str
    share_url: str
    ctx_recon: str
    event_uid: str | None = None
    event_summary: str | None = None
    # ISO 8601 strings (timezone aware) for the planned departure/arrival, if known.
    planned_departure: str | None = None
    planned_arrival: str | None = None
    resolved_at: str | None = None

    @property
    def planned_departure_dt(self) -> datetime | None:
        """Return the planned departure as an aware datetime, if parseable."""
        return _parse_dt(self.planned_departure)

    @property
    def planned_arrival_dt(self) -> datetime | None:
        """Return the planned arrival as an aware datetime, if parseable."""
        return _parse_dt(self.planned_arrival)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the Store."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredTrip:
        """Deserialize from the Store, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(value)


@dataclass
class TripStore:
    """In-memory cache of trips backed by a Home Assistant Store."""

    hass: HomeAssistant
    entry_id: str
    _store: Store = field(init=False)
    _trips: dict[str, StoredTrip] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._store = Store(
            self.hass, STORAGE_VERSION, f"{DOMAIN}.{self.entry_id}"
        )

    async def async_load(self) -> None:
        """Load persisted trips into memory."""
        data = await self._store.async_load()
        self._trips = {}
        if not data:
            return
        for raw in data.get("trips", []):
            try:
                trip = StoredTrip.from_dict(raw)
            except TypeError:
                _LOGGER.debug("Skipping malformed stored trip: %s", raw)
                continue
            self._trips[trip.token] = trip

    async def async_save(self) -> None:
        """Persist current trips."""
        await self._store.async_save(
            {"trips": [t.to_dict() for t in self._trips.values()]}
        )

    async def async_remove(self) -> None:
        """Remove the underlying store file (on entry removal)."""
        await self._store.async_remove()

    @property
    def trips(self) -> list[StoredTrip]:
        """Return all stored trips."""
        return list(self._trips.values())

    def get(self, token: str) -> StoredTrip | None:
        """Return a stored trip by token, if present."""
        return self._trips.get(token)

    def upsert(self, trip: StoredTrip) -> None:
        """Insert or update a trip in memory (call async_save to persist)."""
        self._trips[trip.token] = trip

    def remove(self, token: str) -> bool:
        """Remove a trip by token. Returns True if something was removed."""
        return self._trips.pop(token, None) is not None

    def reconcile_present(
        self, found_tokens: set[str], now: datetime, horizon: datetime
    ) -> int:
        """Drop upcoming trips whose token is no longer in the calendar.

        Only trips departing between ``now`` and ``horizon`` are considered, so a
        deleted calendar event is removed while past trips (handled by pruning)
        and trips beyond the scan window are left untouched. Returns the number
        of trips removed.
        """
        removed: list[str] = []
        for token, trip in self._trips.items():
            if token in found_tokens:
                continue
            departure = trip.planned_departure_dt
            if departure is None:
                continue
            if now <= departure <= horizon:
                removed.append(token)
        for token in removed:
            del self._trips[token]
        return len(removed)

    def prune_before(self, cutoff: datetime) -> int:
        """Drop trips whose planned arrival (or departure) is before cutoff.

        Returns the number of trips removed.
        """
        removed: list[str] = []
        for token, trip in self._trips.items():
            reference = trip.planned_arrival_dt or trip.planned_departure_dt
            # Keep trips we can't place in time; they may still resolve later.
            if reference is not None and reference < cutoff:
                removed.append(token)
        for token in removed:
            del self._trips[token]
        return len(removed)

    def next_upcoming(self, now: datetime, grace: datetime) -> StoredTrip | None:
        """Return the nearest trip that has not yet finished.

        A trip is considered current until its planned arrival passes the grace
        cutoff. Among candidates, the earliest planned departure wins.
        """
        candidates: list[StoredTrip] = []
        for trip in self._trips.values():
            arrival = trip.planned_arrival_dt
            departure = trip.planned_departure_dt
            end_reference = arrival or departure
            if end_reference is None:
                continue
            if end_reference >= grace:
                candidates.append(trip)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda t: t.planned_departure_dt or t.planned_arrival_dt or now,
        )
