"""Standalone verification of the ctxRecon encoding against the real example.

Mirrors the pure helpers in custom_components/ns_caldav/ns_api.py using only the
standard library, so it can run without Home Assistant / aiohttp installed.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

_CTX_RE = re.compile(r"(?:ctxRecon|ctx)=([^&]+)")
_CTX_SAFE = "=:,"


def extract_ctx_recon(url: str) -> str | None:
    m = _CTX_RE.search(url)
    return unquote(m.group(1)) if m else None


def encode_ctx_recon_for_api(canonical: str) -> str:
    return quote(canonical, safe=_CTX_SAFE)


def parse_planned_times(canonical: str):
    dep = arr = None
    for part in canonical.split("|"):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        if key == "plannedFromTime":
            dep = value
        elif key == "plannedArrivalTime":
            arr = value
    return dep, arr


RESOLVED_URL = (
    "https://www.ns.nl/reisplanner/#/?type=vertrek&tijd=2026-07-01T07%3A42&"
    "ctxRecon=arnu%7CfromLocation%3D51.922081%2C4.463926%7CoriginName%3D"
    "Zijdewindestraat%2B27%2BB%252C%2BRotterdam%7CtoLocation%3D52.331359%2C"
    "4.923347%7CdestinationName%3DSpaklerweg%2B52%252C%2BAmsterdam-Duivendrecht"
    "%7CoriginWalk%3Dtrue%7CdestinationWalk%3Dtrue%7CplannedFromTime%3D"
    "2026-07-01T07%3A42%3A00%2B02%3A00%7CplannedArrivalTime%3D2026-07-01T08%3A"
    "50%3A00%2B02%3A00%7CexcludeHighSpeedTrains%3Dfalse%7CsearchForAccessibleTrip"
    "%3Dfalse%7ClocalTrainsOnly%3Dfalse%7CdisabledTransportModalities%3DTRAM%2C"
    "FERRY%2CMETRO%2CBUS%7CtravelAssistance%3Dfalse%7CtripSummaryHash%3D1334580018"
    "&vertrektype=latlong&vertrek=51.922081%2C4.463926"
)

EXPECTED_API_CTX = (
    "arnu%7CfromLocation=51.922081,4.463926%7CoriginName=Zijdewindestraat%2B27"
    "%2BB%252C%2BRotterdam%7CtoLocation=52.331359,4.923347%7CdestinationName="
    "Spaklerweg%2B52%252C%2BAmsterdam-Duivendrecht%7CoriginWalk=true%7C"
    "destinationWalk=true%7CplannedFromTime=2026-07-01T07:42:00%2B02:00%7C"
    "plannedArrivalTime=2026-07-01T08:50:00%2B02:00%7CexcludeHighSpeedTrains="
    "false%7CsearchForAccessibleTrip=false%7ClocalTrainsOnly=false%7C"
    "disabledTransportModalities=TRAM,FERRY,METRO,BUS%7CtravelAssistance=false"
    "%7CtripSummaryHash=1334580018"
)


def main() -> int:
    canonical = extract_ctx_recon(RESOLVED_URL)
    assert canonical is not None, "Failed to extract ctxRecon"
    api = encode_ctx_recon_for_api(canonical)
    dep, arr = parse_planned_times(canonical)

    print("Canonical:", canonical)
    print("API form :", api)
    print("Planned departure:", dep)
    print("Planned arrival  :", arr)

    ok = api == EXPECTED_API_CTX
    if not ok:
        # Show first difference for debugging.
        for i, (a, b) in enumerate(zip(api, EXPECTED_API_CTX)):
            if a != b:
                print(f"First diff at {i}: got {a!r} expected {b!r}")
                print("got     :", api[max(0, i - 20):i + 20])
                print("expected:", EXPECTED_API_CTX[max(0, i - 20):i + 20])
                break
        if len(api) != len(EXPECTED_API_CTX):
            print(f"Length mismatch: got {len(api)} expected {len(EXPECTED_API_CTX)}")

    assert dep == "2026-07-01T07:42:00+02:00", dep
    assert arr == "2026-07-01T08:50:00+02:00", arr
    print("\nMATCH:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
