"""Data update coordinators for discovery and adaptive trip polling."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .caldav_client import async_discover_share_links
from .const import (
    CONF_LOOK_AHEAD_DAYS,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SUBSCRIPTION_KEY,
    DEFAULT_LOOK_AHEAD_DAYS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    POLL_INTERVAL_FAR_SECONDS,
    POLL_INTERVAL_IN_PROGRESS_SECONDS,
    POLL_TIERS,
    TRIP_GRACE_MINUTES,
)
from .model import ParsedTrip, parse_trip
from .ns_api import NsApiClient, NsApiError, NsAuthError, parse_planned_times
from .storage import StoredTrip, TripStore

_LOGGER = logging.getLogger(__name__)


class DiscoveryCoordinator(DataUpdateCoordinator[int]):
    """Hourly scan of the calendar; resolves new share links into the store."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: TripStore,
        client: NsApiClient,
    ) -> None:
        scan_hours = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_discovery",
            update_interval=timedelta(hours=scan_hours),
        )
        self._entry = entry
        self._store = store
        self._client = client
        # Set by __init__.py after both coordinators exist.
        self.trip_coordinator: TripCoordinator | None = None

    async def _async_update_data(self) -> int:
        data = self._entry.data
        look_ahead = self._entry.options.get(
            CONF_LOOK_AHEAD_DAYS, DEFAULT_LOOK_AHEAD_DAYS
        )
        try:
            hits = await async_discover_share_links(
                self.hass,
                data[CONF_URL],
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                look_ahead,
            )
        except Exception as err:  # noqa: BLE001 - surfaced as UpdateFailed
            raise UpdateFailed(f"Calendar scan failed: {err}") from err

        changed = False
        for hit in hits:
            existing = self._store.get(hit.token)
            if existing and existing.ctx_recon:
                # Refresh event metadata if it changed, but don't re-resolve.
                if existing.event_summary != hit.event_summary:
                    existing.event_summary = hit.event_summary
                    changed = True
                continue
            try:
                ctx_recon = await self._client.resolve_share_url(hit.share_url)
            except NsApiError as err:
                _LOGGER.warning(
                    "Could not resolve share link %s: %s", hit.share_url, err
                )
                continue
            if not ctx_recon:
                _LOGGER.debug(
                    "No ctxRecon found for share link %s", hit.share_url
                )
                continue
            planned_dep, planned_arr = parse_planned_times(ctx_recon)
            self._store.upsert(
                StoredTrip(
                    token=hit.token,
                    share_url=hit.share_url,
                    ctx_recon=ctx_recon,
                    event_uid=hit.event_uid,
                    event_summary=hit.event_summary,
                    planned_departure=planned_dep,
                    planned_arrival=planned_arr,
                    resolved_at=dt_util.now().isoformat(),
                )
            )
            changed = True

        # Prune trips that finished well in the past.
        cutoff = dt_util.now() - timedelta(days=1)
        if self._store.prune_before(cutoff):
            changed = True

        if changed:
            await self._store.async_save()
            if self.trip_coordinator is not None:
                await self.trip_coordinator.async_request_refresh()

        return len(self._store.trips)


class TripCoordinator(DataUpdateCoordinator[ParsedTrip | None]):
    """Adaptive polling of the NS API for the nearest upcoming trip."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: TripStore,
        client: NsApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_trip",
            update_interval=timedelta(seconds=POLL_INTERVAL_FAR_SECONDS),
        )
        self._entry = entry
        self._store = store
        self._client = client
        self.current_trip: StoredTrip | None = None

    def _select_interval(self, parsed: ParsedTrip | None) -> timedelta:
        if parsed is None or parsed.actual_departure is None:
            return timedelta(seconds=POLL_INTERVAL_FAR_SECONDS)
        now = dt_util.now()
        if now >= parsed.actual_departure:
            return timedelta(seconds=POLL_INTERVAL_IN_PROGRESS_SECONDS)
        minutes_until = (parsed.actual_departure - now).total_seconds() / 60
        for threshold_min, interval_s in POLL_TIERS:
            if minutes_until <= threshold_min:
                return timedelta(seconds=interval_s)
        return timedelta(seconds=POLL_INTERVAL_FAR_SECONDS)

    async def _async_update_data(self) -> ParsedTrip | None:
        now = dt_util.now()
        grace = now - timedelta(minutes=TRIP_GRACE_MINUTES)
        stored = self._store.next_upcoming(now, grace)
        self.current_trip = stored

        if stored is None:
            self.update_interval = timedelta(seconds=POLL_INTERVAL_FAR_SECONDS)
            return None

        try:
            raw = await self._client.get_trip(stored.ctx_recon)
        except NsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NsApiError as err:
            raise UpdateFailed(f"NS API request failed: {err}") from err

        parsed = parse_trip(raw)
        self.update_interval = self._select_interval(parsed)
        return parsed
