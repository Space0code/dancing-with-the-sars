"""Recorded wildfires: EFFIS burnt-area perimeters (European Commission JRC, Copernicus), free and without a key.

Service: WFS 2.0.0 at ``maps.effis.emergency.copernicus.eu/effis``, layer ``ms:modis.ba.poly`` (burnt areas mapped from
MODIS since 2016, updated every few days, all of Europe: French fires near the border are in the answer too). Each
polygon has ``FIREDATE`` / ``FINALDATE`` (``YYYY-MM-DD HH:MM:SS``), ``AREA_HA`` (a whole number, as a string) and
``COMMUNE`` (the only place name: there is no fire name). Licence CC BY 4.0: credit "EFFIS, European Commission Joint
Research Centre / Copernicus Emergency Management Service".
**Axis order:** the WFS ``bbox`` takes latitude first (``lat,lon,lat,lon,urn:ogc:def:crs:EPSG::4326``); the GeoJSON it
returns is lon, lat. We send only the polygon's bounding box and intersect the perimeters ourselves, in metres.
Fires under about 20 ha are not mapped by MODIS, so "no fire recorded" only rules out larger fires.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from shapely.geometry import shape

from ._common import fetch, safe, to_utm

SOURCE = "EFFIS burnt areas (European Commission JRC / Copernicus Emergency Management Service)"
SERVICE = "https://maps.effis.emergency.copernicus.eu/effis"
VIEWER = "https://forest-fire.emergency.copernicus.eu/apps/effis.statistics/estimates"
LAYER = "ms:modis.ba.poly"
MIN_OVERLAP = 0.5  # share of the change polygon inside a fire perimeter for the fire to count as "recorded"
WINDOW_DAYS = 365  # with ``until``: the fire must have ended no more than this long before it


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, since: str | None = None, until: str | None = None, **options) -> dict:
    """``recorded`` (bool: at least ``MIN_OVERLAP`` of the polygon lies inside a mapped fire) and ``fires``
    (``[{name, date, end, area_ha, overlap_share, country}]``, biggest overlap first). ``since="YYYY-MM-DD"`` drops
    fires that ended before that day; ``until="YYYY-MM-DD"`` drops fires that started after it or that ended more than
    ``WINDOW_DAYS`` before it (a burn scar from years ago does not explain a change today)."""
    g = to_utm(geometry)
    lon0, lat0, lon1, lat1 = shape(geometry).bounds
    body = fetch("fire", SERVICE, {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": LAYER,
        "outputFormat": "application/json; subtype=geojson",
        "bbox": f"{lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4326",
        "propertyName": "id,FIREDATE,FINALDATE,AREA_HA,COMMUNE,PROVINCE,COUNTRY",
    })
    lo = _day(since)
    hi = _day(until)
    fires = []
    for f in json.loads(body)["features"]:
        p = f["properties"]
        start = _day(p.get("FIREDATE"))
        end = _day(p.get("FINALDATE")) or start
        if lo and end and end < lo:
            continue
        if hi and start and start > hi:
            continue
        if hi and end and end < hi - timedelta(days=WINDOW_DAYS):
            continue
        share = to_utm(f["geometry"]).intersection(g).area / g.area
        if share <= 0:
            continue
        try:
            area_ha = float(p.get("AREA_HA"))
        except (TypeError, ValueError):
            area_ha = None
        fires.append({
            "name": p.get("COMMUNE") or "unnamed fire",
            "date": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "area_ha": area_ha,
            "overlap_share": round(share, 3),
            "country": p.get("COUNTRY"),
        })
    fires.sort(key=lambda x: -x["overlap_share"])
    return {"recorded": any(x["overlap_share"] >= MIN_OVERLAP for x in fires), "fires": fires}
