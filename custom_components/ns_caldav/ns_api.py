"""NS API client: resolve share links and fetch trips.

Two responsibilities:

1. ``resolve_share_url`` follows the redirect chain from a ``ns.nl/rpx?s=...``
   share link until it reaches a URL carrying a ``ctxRecon`` parameter, and
   returns that ctxRecon in its canonical (once-decoded) form.
2. ``get_trip`` calls the NS Reisinformatie API with that ctxRecon.

ctxRecon encoding is fiddly: the share URL carries it in the fragment, double
percent-encoded. We decode exactly once to the canonical value (which equals the
``ctxRecon`` field the API itself returns) and re-encode with a safe set that
mirrors what the NS API expects. See ``encode_ctx_recon_for_api`` and its tests.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, unquote, urljoin

import aiohttp
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    HTTP_TIMEOUT,
    MAX_REDIRECTS,
    NS_API_FIXED_PARAMS,
    NS_API_TRIP_URL,
)

_LOGGER = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
# Matches ctxRecon (or the shorter ctx) parameter value in a URL/fragment.
_CTX_RE = re.compile(r"(?:ctxRecon|ctx)=([^&]+)")
# Characters the NS API expects to remain literal inside the ctxRecon value.
_CTX_SAFE = "=:,"


class NsApiError(Exception):
    """Generic NS API error."""


class NsAuthError(NsApiError):
    """Raised when the subscription key is missing or invalid."""


def extract_ctx_recon(url: str) -> str | None:
    """Return the canonical ctxRecon from a URL, or None if absent.

    "Canonical" means decoded exactly once, matching the ``ctxRecon`` value the
    NS API returns in its responses.
    """
    match = _CTX_RE.search(url)
    if not match:
        return None
    return unquote(match.group(1))


def encode_ctx_recon_for_api(canonical_ctx_recon: str) -> str:
    """Encode a canonical ctxRecon into the form the NS API expects.

    Keeps ``= : ,`` literal while percent-encoding ``|`` -> %7C, ``+`` -> %2B,
    and ``%`` -> %25 (so a literal ``%2C`` becomes ``%252C``).
    """
    return quote(canonical_ctx_recon, safe=_CTX_SAFE)


def build_trip_url(canonical_ctx_recon: str) -> str:
    """Build the full, pre-encoded trip request URL."""
    encoded = encode_ctx_recon_for_api(canonical_ctx_recon)
    return f"{NS_API_TRIP_URL}?ctxRecon={encoded}&{NS_API_FIXED_PARAMS}"


def parse_planned_times(canonical_ctx_recon: str) -> tuple[str | None, str | None]:
    """Extract planned departure/arrival ISO strings from a ctxRecon.

    The ctxRecon is a ``|``-delimited list of ``key=value`` pairs and already
    carries ``plannedFromTime`` and ``plannedArrivalTime``, so we can determine a
    trip's timing without an API call during discovery.
    """
    departure: str | None = None
    arrival: str | None = None
    for part in canonical_ctx_recon.split("|"):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        if key == "plannedFromTime":
            departure = value
        elif key == "plannedArrivalTime":
            arrival = value
    return departure, arrival


class NsApiClient:
    """Thin async client around the NS share/redirect and trip endpoints."""

    def __init__(self, hass: HomeAssistant, subscription_key: str) -> None:
        self._session = async_get_clientsession(hass)
        self._subscription_key = subscription_key

    async def resolve_share_url(self, share_url: str) -> str | None:
        """Follow redirects from a share URL until a ctxRecon is found.

        Returns the canonical ctxRecon, or None if none was reached.
        """
        current = share_url
        for _ in range(MAX_REDIRECTS):
            if (ctx := extract_ctx_recon(current)) is not None:
                return ctx
            try:
                async with self._session.get(
                    current,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
                ) as resp:
                    location = resp.headers.get("Location")
                    if resp.status not in _REDIRECT_STATUSES or not location:
                        # Reached a non-redirect; check its final URL too.
                        return extract_ctx_recon(str(resp.url)) or extract_ctx_recon(
                            current
                        )
            except aiohttp.ClientError as err:
                raise NsApiError(f"Error resolving share URL: {err}") from err
            current = urljoin(current, location)

        # Exhausted redirects; last attempt at the final URL.
        return extract_ctx_recon(current)

    async def get_trip(self, canonical_ctx_recon: str) -> dict:
        """Fetch the trip for a canonical ctxRecon."""
        if not self._subscription_key:
            raise NsAuthError("Missing NS subscription key")

        url = URL(build_trip_url(canonical_ctx_recon), encoded=True)
        headers = {
            "Ocp-Apim-Subscription-Key": self._subscription_key,
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        }
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                if resp.status in (401, 403):
                    raise NsAuthError(
                        f"NS API rejected subscription key (HTTP {resp.status})"
                    )
                if resp.status != 200:
                    text = await resp.text()
                    raise NsApiError(
                        f"NS API returned HTTP {resp.status}: {text[:200]}"
                    )
                return await resp.json()
        except aiohttp.ClientError as err:
            raise NsApiError(f"Error fetching trip: {err}") from err
