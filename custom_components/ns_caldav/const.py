"""Constants for the NS CalDAV Trip integration."""

from __future__ import annotations

import re
from typing import Final

DOMAIN: Final = "ns_caldav"

# Config entry keys (CONF_URL / CONF_USERNAME / CONF_PASSWORD / CONF_VERIFY_SSL
# come from homeassistant.const).
CONF_SUBSCRIPTION_KEY: Final = "subscription_key"

# Options keys.
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"
CONF_LOOK_AHEAD_DAYS: Final = "look_ahead_days"
CONF_NOTIFY_LEAD_MINUTES: Final = "notify_lead_minutes"
CONF_DELAY_THRESHOLD_MINUTES: Final = "delay_threshold_minutes"

# Defaults.
DEFAULT_SCAN_INTERVAL_HOURS: Final = 1
DEFAULT_LOOK_AHEAD_DAYS: Final = 30
DEFAULT_NOTIFY_LEAD_MINUTES: Final = 10
DEFAULT_DELAY_THRESHOLD_MINUTES: Final = 1
DEFAULT_VERIFY_SSL: Final = True

# Network timeouts (seconds).
CALDAV_TIMEOUT: Final = 30
HTTP_TIMEOUT: Final = 30

# Adaptive poll tiers: ordered (minutes_until_departure_threshold, poll_interval_seconds).
# Evaluated top to bottom; the first tier whose threshold is >= minutes-until-departure
# wins. The final entry (None) is the fallback for far-future trips.
POLL_TIERS: Final = (
    (20, 120),  # within 20 min -> every 2 min
    (120, 900),  # within 2 h    -> every 15 min
)
POLL_INTERVAL_FAR_SECONDS: Final = 3600  # > 2 h away -> hourly
# Keep showing / polling a trip until this many minutes after its (actual) arrival.
TRIP_GRACE_MINUTES: Final = 5
# Poll cadence while a trip is in progress (between departure and arrival).
POLL_INTERVAL_IN_PROGRESS_SECONDS: Final = 120

# NS API.
NS_API_TRIP_URL: Final = (
    "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/trips/trip"
)
NS_API_FIXED_PARAMS: Final = (
    "travelRequestType=DEFAULT"
    "&sourceCtxRecon=false"
    "&discount=NO_DISCOUNT"
    "&travelClass=2"
)

# Match NS share links of the form https://www.ns.nl/rpx?s=TOKEN
NS_SHARE_URL_RE: Final = re.compile(
    r"https://www\.ns\.nl/rpx\?s=(?P<token>[A-Za-z0-9_-]+)"
)
# Maximum redirects to follow when resolving a share link.
MAX_REDIRECTS: Final = 10

# Storage.
STORAGE_VERSION: Final = 1

# Public-transit leg travel type as returned by the NS API.
PUBLIC_TRANSIT_TYPE: Final = "PUBLIC_TRANSIT"

PLATFORMS: Final = ["sensor", "binary_sensor"]
