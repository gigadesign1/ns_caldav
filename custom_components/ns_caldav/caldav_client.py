"""CalDAV access for discovering NS share links in calendar events.

The ``caldav`` and ``icalendar`` libraries are synchronous (caldav uses
``requests`` under the hood), so every network/parse call here is meant to be
run inside Home Assistant's executor via ``hass.async_add_executor_job``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

import caldav
from caldav.lib.error import AuthorizationError, DAVError
import requests

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CALDAV_TIMEOUT, NS_SHARE_URL_RE

_LOGGER = logging.getLogger(__name__)

# Fields on a VEVENT we scan for NS share links.
_SCANNED_FIELDS = ("SUMMARY", "DESCRIPTION", "LOCATION", "URL", "X-ALT-DESC")


@dataclass(frozen=True)
class ShareLinkHit:
    """A discovered NS share link and the event it came from."""

    token: str
    share_url: str
    event_uid: str | None
    event_summary: str | None


def _build_client(
    url: str, username: str, password: str, verify_ssl: bool
) -> caldav.DAVClient:
    return caldav.DAVClient(
        url,
        username=username,
        password=password,
        ssl_verify_cert=verify_ssl,
        timeout=CALDAV_TIMEOUT,
    )


def validate_connection(
    url: str, username: str, password: str, verify_ssl: bool
) -> str | None:
    """Validate CalDAV credentials. Returns an error key or None on success.

    Runs synchronously; call via the executor.
    """
    client = _build_client(url, username, password, verify_ssl)
    try:
        client.principal()
    except AuthorizationError as err:
        _LOGGER.warning("Authorization error connecting to CalDAV: %s", err)
        if getattr(err, "reason", None) == "Unauthorized":
            return "invalid_auth"
        return "cannot_connect"
    except requests.Timeout as err:
        _LOGGER.warning("Timeout connecting to CalDAV: %s", err)
        return "cannot_connect"
    except requests.ConnectionError as err:
        _LOGGER.warning("Connection error connecting to CalDAV: %s", err)
        return "cannot_connect"
    except DAVError as err:
        _LOGGER.warning("CalDAV client error: %s", err)
        return "cannot_connect"
    except Exception:  # noqa: BLE001 - surface as generic unknown error
        _LOGGER.exception("Unexpected error validating CalDAV connection")
        return "unknown"
    return None


def _component_text(component: Any, field: str) -> str | None:
    value = component.get(field)
    if value is None:
        return None
    # icalendar may return vText or similar; str() yields the decoded text.
    return str(value)


def _scan_event(event: caldav.Event) -> list[ShareLinkHit]:
    hits: list[ShareLinkHit] = []
    try:
        calendar = event.icalendar_instance
    except Exception:  # noqa: BLE001 - skip events we cannot parse
        _LOGGER.debug("Could not parse an event, skipping", exc_info=True)
        return hits

    for component in calendar.walk("VEVENT"):
        uid = _component_text(component, "UID")
        summary = _component_text(component, "SUMMARY")
        seen_tokens: set[str] = set()
        for field in _SCANNED_FIELDS:
            text = _component_text(component, field)
            if not text:
                continue
            for match in NS_SHARE_URL_RE.finditer(text):
                token = match.group("token")
                if token in seen_tokens:
                    continue
                seen_tokens.add(token)
                hits.append(
                    ShareLinkHit(
                        token=token,
                        share_url=match.group(0),
                        event_uid=uid,
                        event_summary=summary,
                    )
                )
    return hits


def discover_share_links(
    url: str,
    username: str,
    password: str,
    verify_ssl: bool,
    look_ahead_days: int,
) -> list[ShareLinkHit]:
    """Scan upcoming calendar events for NS share links (run via executor)."""
    client = _build_client(url, username, password, verify_ssl)
    principal = client.principal()
    start = dt_util.now()
    end = start + timedelta(days=look_ahead_days)

    hits_by_token: dict[str, ShareLinkHit] = {}
    for calendar in principal.calendars():
        try:
            events = calendar.search(
                start=start, end=end, event=True, expand=True
            )
        except (DAVError, requests.RequestException) as err:
            _LOGGER.warning(
                "Failed to search calendar %s: %s",
                getattr(calendar, "name", calendar),
                err,
            )
            continue
        for event in events:
            for hit in _scan_event(event):
                # First occurrence of a token wins; later duplicates ignored.
                hits_by_token.setdefault(hit.token, hit)

    return list(hits_by_token.values())


async def async_discover_share_links(
    hass: HomeAssistant,
    url: str,
    username: str,
    password: str,
    verify_ssl: bool,
    look_ahead_days: int,
) -> list[ShareLinkHit]:
    """Async wrapper running the blocking CalDAV scan in the executor."""
    return await hass.async_add_executor_job(
        discover_share_links,
        url,
        username,
        password,
        verify_ssl,
        look_ahead_days,
    )


async def async_validate_connection(
    hass: HomeAssistant,
    url: str,
    username: str,
    password: str,
    verify_ssl: bool,
) -> str | None:
    """Async wrapper for credential validation."""
    return await hass.async_add_executor_job(
        validate_connection, url, username, password, verify_ssl
    )
