"""Parsing helpers that turn the raw NS trip JSON into entity-friendly data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import PUBLIC_TRANSIT_TYPE


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(str(value))


def _delay_minutes(planned: datetime | None, actual: datetime | None) -> int:
    if planned is None or actual is None:
        return 0
    return max(0, round((actual - planned).total_seconds() / 60))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass
class StationInfo:
    """Departure/arrival station details derived from a leg endpoint."""

    name: str | None = None
    planned_time: datetime | None = None
    actual_time: datetime | None = None
    delay_minutes: int = 0
    track: str | None = None
    uic_code: str | None = None

    def as_attributes(self) -> dict[str, Any]:
        """Return a JSON-serializable attribute dict."""
        return {
            "name": self.name,
            "planned_time": _iso(self.planned_time),
            "actual_time": _iso(self.actual_time),
            "delay_minutes": self.delay_minutes,
            "track": self.track,
            "uic_code": self.uic_code,
        }


def _station_from_point(point: dict[str, Any]) -> StationInfo:
    planned = _parse(point.get("plannedDateTime"))
    actual = _parse(point.get("actualDateTime")) or planned
    return StationInfo(
        name=point.get("name"),
        planned_time=planned,
        actual_time=actual,
        delay_minutes=_delay_minutes(planned, actual),
        track=point.get("actualTrack") or point.get("plannedTrack"),
        uic_code=point.get("uicCode"),
    )


@dataclass
class ParsedTrip:
    """Normalized view over a single NS trip used by all entities."""

    # Door-to-door endpoints (first leg origin / last leg destination).
    origin_name: str | None = None
    destination_name: str | None = None
    planned_departure: datetime | None = None
    actual_departure: datetime | None = None
    planned_arrival: datetime | None = None
    actual_arrival: datetime | None = None
    departure_delay_minutes: int = 0
    arrival_delay_minutes: int = 0

    duration_minutes: int | None = None
    transfers: int | None = None
    status: str | None = None
    crowd_forecast: str | None = None

    # Station-level (first/last public-transit leg).
    departure_station: StationInfo = field(default_factory=StationInfo)
    arrival_station: StationInfo = field(default_factory=StationInfo)

    price_eur: float | None = None
    supplement_eur: float | None = None
    total_price_eur: float | None = None

    messages: list[dict[str, Any]] = field(default_factory=list)
    legs: list[dict[str, Any]] = field(default_factory=list)
    share_url: str | None = None
    summary_text: str | None = None

    @property
    def is_delayed(self) -> bool:
        """True if departure or arrival has any delay."""
        return self.departure_delay_minutes > 0 or self.arrival_delay_minutes > 0

    @property
    def is_disrupted(self) -> bool:
        """True if the trip is anything other than a NORMAL status, or messaged."""
        if self.status and self.status != "NORMAL":
            return True
        return bool(self.messages)


def _money(cents: Any) -> float | None:
    if cents is None:
        return None
    try:
        return round(int(cents) / 100, 2)
    except (TypeError, ValueError):
        return None


def _normalize_leg(leg: dict[str, Any]) -> dict[str, Any]:
    origin = leg.get("origin", {})
    destination = leg.get("destination", {})
    product = leg.get("product", {})
    o_planned = _parse(origin.get("plannedDateTime"))
    o_actual = _parse(origin.get("actualDateTime")) or o_planned
    d_planned = _parse(destination.get("plannedDateTime"))
    d_actual = _parse(destination.get("actualDateTime")) or d_planned
    return {
        "type": leg.get("travelType"),
        "name": product.get("displayName") or leg.get("name"),
        "code": leg.get("name"),
        "direction": leg.get("direction"),
        "from": origin.get("name"),
        "to": destination.get("name"),
        "departure": _iso(o_actual),
        "arrival": _iso(d_actual),
        "departure_track": origin.get("actualTrack") or origin.get("plannedTrack"),
        "arrival_track": destination.get("actualTrack")
        or destination.get("plannedTrack"),
        "departure_delay_minutes": _delay_minutes(o_planned, o_actual),
        "arrival_delay_minutes": _delay_minutes(d_planned, d_actual),
        "duration_minutes": leg.get("actualDurationInMinutes")
        or leg.get("plannedDurationInMinutes"),
        "distance_meters": leg.get("distanceInMeters"),
        "cancelled": leg.get("cancelled", False),
        "part_cancelled": leg.get("partCancelled", False),
    }


def _build_summary_text(trip: ParsedTrip, transit_legs: list[dict[str, Any]]) -> str:
    dep = trip.departure_station
    arr = trip.arrival_station

    def _hhmm(value: datetime | None) -> str:
        return value.strftime("%H:%M") if value else "?"

    parts: list[str] = []
    dep_track = f" (spoor {dep.track})" if dep.track else ""
    arr_track = f" (spoor {arr.track})" if arr.track else ""
    parts.append(
        f"{dep.name or trip.origin_name} {_hhmm(dep.actual_time)}{dep_track}"
        f" -> {arr.name or trip.destination_name} {_hhmm(arr.actual_time)}{arr_track}"
    )

    if transit_legs:
        first = transit_legs[0]
        code = first.get("name")
        display = (first.get("product") or {}).get("displayName")
        if display and code and code != display:
            train = f"{display} ({code})"
        else:
            train = display or code
        if train:
            direction = first.get("direction")
            parts.append(f"{train} ri. {direction}" if direction else train)

    if trip.transfers is not None:
        parts.append(f"{trip.transfers} overstappen")

    if trip.status and trip.status != "NORMAL":
        parts.append(trip.status.lower())
    elif trip.is_delayed:
        delay = max(trip.departure_delay_minutes, trip.arrival_delay_minutes)
        parts.append(f"+{delay} min vertraging")
    else:
        parts.append("op tijd")

    return ", ".join(parts)


def parse_trip(data: dict[str, Any]) -> ParsedTrip | None:
    """Parse a raw NS trip dict into a :class:`ParsedTrip`.

    Returns None when the payload has no usable legs.
    """
    legs = data.get("legs") or []
    if not legs:
        return None

    first_leg = legs[0]
    last_leg = legs[-1]
    first_origin = first_leg.get("origin", {})
    last_destination = last_leg.get("destination", {})

    planned_departure = _parse(first_origin.get("plannedDateTime"))
    actual_departure = _parse(first_origin.get("actualDateTime")) or planned_departure
    planned_arrival = _parse(last_destination.get("plannedDateTime"))
    actual_arrival = _parse(last_destination.get("actualDateTime")) or planned_arrival

    transit_legs = [
        leg for leg in legs if leg.get("travelType") == PUBLIC_TRANSIT_TYPE
    ]
    # Station-level endpoints: first boarding and final alighting station.
    if transit_legs:
        departure_station = _station_from_point(transit_legs[0].get("origin", {}))
        arrival_station = _station_from_point(
            transit_legs[-1].get("destination", {})
        )
    else:
        departure_station = _station_from_point(first_origin)
        arrival_station = _station_from_point(last_destination)

    product_fare = data.get("productFare", {}) or {}
    share = data.get("shareUrl", {}) or {}

    trip = ParsedTrip(
        origin_name=first_origin.get("name"),
        destination_name=last_destination.get("name"),
        planned_departure=planned_departure,
        actual_departure=actual_departure,
        planned_arrival=planned_arrival,
        actual_arrival=actual_arrival,
        departure_delay_minutes=_delay_minutes(planned_departure, actual_departure),
        arrival_delay_minutes=_delay_minutes(planned_arrival, actual_arrival),
        duration_minutes=data.get("actualDurationInMinutes")
        or data.get("plannedDurationInMinutes"),
        transfers=data.get("transfers"),
        status=data.get("status"),
        crowd_forecast=data.get("crowdForecast"),
        departure_station=departure_station,
        arrival_station=arrival_station,
        price_eur=_money(product_fare.get("priceInCentsExcludingSupplement")),
        supplement_eur=_money(product_fare.get("supplementInCents")),
        total_price_eur=_money(product_fare.get("buyableTicketPriceInCents"))
        or _money(product_fare.get("priceInCents")),
        messages=list(data.get("messages") or []),
        legs=[_normalize_leg(leg) for leg in legs],
        share_url=share.get("uri"),
    )
    # Account for cancelled legs in the disruption signal.
    if any(
        leg.get("cancelled") or leg.get("partCancelled") for leg in legs
    ) and (trip.status == "NORMAL" or trip.status is None):
        trip.status = "DISRUPTION"

    trip.summary_text = _build_summary_text(trip, transit_legs)
    return trip
