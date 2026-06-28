"""Validate model.parse_trip against the example trip without a full HA install.

Provides a minimal stub for ``homeassistant.util.dt`` so the real model module
can be imported and exercised.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from datetime import datetime
from pathlib import Path

# --- Stub the small slice of Home Assistant that model.py imports ----------
_OFFSET_RE = re.compile(r"([+-]\d{2})(\d{2})$")


def _parse_datetime(value):
    if not value:
        return None
    text = str(value)
    # Normalize "+0200" -> "+02:00" for datetime.fromisoformat.
    text = _OFFSET_RE.sub(r"\1:\2", text)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


dt_module = types.ModuleType("homeassistant.util.dt")
dt_module.parse_datetime = _parse_datetime

util_module = types.ModuleType("homeassistant.util")
util_module.dt = dt_module

ha_module = types.ModuleType("homeassistant")
ha_module.util = util_module

sys.modules["homeassistant"] = ha_module
sys.modules["homeassistant.util"] = util_module
sys.modules["homeassistant.util.dt"] = dt_module

# --- Import the real model module by path -----------------------------------
MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "ns_caldav"
    / "model.py"
)
# const.py is imported by model via relative import; load it as a package.
pkg = types.ModuleType("nscaldavpkg")
pkg.__path__ = [str(MODEL_PATH.parent)]
sys.modules["nscaldavpkg"] = pkg

const_spec = importlib.util.spec_from_file_location(
    "nscaldavpkg.const", MODEL_PATH.parent / "const.py"
)
const_mod = importlib.util.module_from_spec(const_spec)
sys.modules["nscaldavpkg.const"] = const_mod
const_spec.loader.exec_module(const_mod)

model_spec = importlib.util.spec_from_file_location("nscaldavpkg.model", MODEL_PATH)
model = importlib.util.module_from_spec(model_spec)
sys.modules["nscaldavpkg.model"] = model
model_spec.loader.exec_module(model)

# --- Example trip (faithful subset of the user's API response) --------------
TRIP = {
    "transfers": 0,
    "status": "NORMAL",
    "crowdForecast": "MEDIUM",
    "actualDurationInMinutes": 68,
    "plannedDurationInMinutes": 68,
    "productFare": {
        "priceInCents": 2190,
        "priceInCentsExcludingSupplement": 1870,
        "supplementInCents": 320,
        "buyableTicketPriceInCents": 2190,
    },
    "shareUrl": {"uri": "https://www.ns.nl/rpx?ctx=example"},
    "legs": [
        {
            "travelType": "WALK",
            "origin": {
                "name": "Zijdewindestraat 27 B, Rotterdam",
                "plannedDateTime": "2026-07-01T07:42:00+0200",
            },
            "destination": {
                "name": "Rotterdam Centraal",
                "plannedDateTime": "2026-07-01T07:51:00+0200",
            },
            "plannedDurationInMinutes": 9,
            "distanceInMeters": 652,
        },
        {
            "travelType": "PUBLIC_TRANSIT",
            "name": "ICD 2421",
            "direction": "Lelystad Centrum",
            "product": {"displayName": "NS Intercity direct"},
            "origin": {
                "name": "Rotterdam Centraal",
                "plannedDateTime": "2026-07-01T07:51:00+0200",
                "actualDateTime": "2026-07-01T07:51:00+0200",
                "plannedTrack": "12",
                "actualTrack": "12",
                "uicCode": "8400530",
            },
            "destination": {
                "name": "Duivendrecht",
                "plannedDateTime": "2026-07-01T08:30:00+0200",
                "actualDateTime": "2026-07-01T08:30:00+0200",
                "plannedTrack": "1",
                "actualTrack": "1",
                "uicCode": "8400194",
            },
            "actualDurationInMinutes": 39,
            "distanceInMeters": 61445,
        },
        {
            "travelType": "WALK",
            "origin": {
                "name": "Duivendrecht",
                "plannedDateTime": "2026-07-01T08:30:00+0200",
            },
            "destination": {
                "name": "Spaklerweg 52, Amsterdam-Duivendrecht",
                "plannedDateTime": "2026-07-01T08:50:00+0200",
            },
            "plannedDurationInMinutes": 20,
            "distanceInMeters": 1596,
        },
    ],
}


def main() -> int:
    trip = model.parse_trip(TRIP)
    assert trip is not None

    checks = {
        "origin_name": (trip.origin_name, "Zijdewindestraat 27 B, Rotterdam"),
        "destination_name": (
            trip.destination_name,
            "Spaklerweg 52, Amsterdam-Duivendrecht",
        ),
        "departure_station": (trip.departure_station.name, "Rotterdam Centraal"),
        "departure_track": (trip.departure_station.track, "12"),
        "arrival_station": (trip.arrival_station.name, "Duivendrecht"),
        "arrival_track": (trip.arrival_station.track, "1"),
        "transfers": (trip.transfers, 0),
        "status": (trip.status, "NORMAL"),
        "crowd": (trip.crowd_forecast, "MEDIUM"),
        "duration": (trip.duration_minutes, 68),
        "price_eur": (trip.price_eur, 18.70),
        "supplement_eur": (trip.supplement_eur, 3.20),
        "total_price_eur": (trip.total_price_eur, 21.90),
        "is_delayed": (trip.is_delayed, False),
        "is_disrupted": (trip.is_disrupted, False),
        "legs_count": (len(trip.legs), 3),
    }
    ok = True
    for label, (got, expected) in checks.items():
        status = "OK" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"[{status}] {label}: {got!r} (expected {expected!r})")

    print("\nsummary_text:", trip.summary_text)
    print("departure_station attrs:", trip.departure_station.as_attributes())
    print("\nALL OK:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
