"""Public-record lookups: "what do public records say about this place?" for a change polygon in Catalonia.

Every module exposes ``lookup(geometry: dict, **options) -> dict``: ``geometry`` is a GeoJSON Polygon or
MultiPolygon in EPSG:4326; the result always has ``source``, ``url``, ``checked`` and, on failure, ``error``; it never
raises. Services, layers and limits: ``kb/data-sources.md`` §3.
"""
from . import cadastre, protected, solar, zoning

LOOKUPS = {"protected": protected.lookup, "cadastre": cadastre.lookup, "zoning": zoning.lookup, "solar": solar.lookup}


def lookup_all(geometry: dict, since: str | None = None) -> dict:
    """Run every lookup; ``since`` goes to the cadastre (buildings built since that date's year)."""
    return {name: (fn(geometry, since=since) if name == "cadastre" else fn(geometry)) for name, fn in LOOKUPS.items()}
