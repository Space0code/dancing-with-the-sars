"""Public-record lookups: "what do public records say about this place?" for a change polygon in Catalonia.

Every module exposes ``lookup(geometry: dict, **options) -> dict``: ``geometry`` is a GeoJSON Polygon or
MultiPolygon in EPSG:4326; the result always has ``source``, ``url``, ``checked`` and, on failure, ``error``; it never
raises. Services, layers and limits: ``kb/data-sources.md`` §3.
"""
from . import cadastre, fire, protected, solar, zoning

LOOKUPS = {
    "protected": protected.lookup, "cadastre": cadastre.lookup, "zoning": zoning.lookup, "solar": solar.lookup,
    "fire": fire.lookup,
}


def lookup_all(geometry: dict, since: str | None = None, until: str | None = None) -> dict:
    """Run every lookup. ``since`` goes to the cadastre (buildings built since that date's year); ``until`` goes to
    the wildfire lookup (only fires that started by then and ended at most a year before)."""
    options = {"cadastre": {"since": since}, "fire": {"until": until}}
    return {name: fn(geometry, **options.get(name, {})) for name, fn in LOOKUPS.items()}
