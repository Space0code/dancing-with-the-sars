"""Optical vegetation-loss alerts as regions: connected groups of confirmed pixels first detected in one month.

Takes the earliest-confirmed-date grid of distalert.combine() and returns one AlertRegion per group: a lon/lat
polygon, geodesic area and the dates a detection needs (kb/multi-sensor-design.md, sections 1-2 and 6).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .distalert import CONFIRMED, Alerts


@dataclass
class AlertRegion:
    month: str                # "YYYY-MM" of first detection
    polygon: dict             # GeoJSON Polygon / MultiPolygon, lon/lat
    area_ha: float            # geodesic area of the polygon (holes excluded)
    pixels: int
    first_date: date          # date of the state that first showed the month's alerts
    not_before: date | None   # date of the state read before it; None for the first state
    last_date: date           # date of the newest state read
    type: str = "clearing"
    confidence: str = "medium"  # confirmed alerts


def to_geojson(geom, ndigits: int = 6) -> dict:
    """Shapely Polygon / MultiPolygon -> GeoJSON dict, rings oriented per RFC 7946 (outer counter-clockwise)."""
    from shapely.geometry import MultiPolygon, mapping
    from shapely.geometry.polygon import orient

    if geom.geom_type == "MultiPolygon":
        geom = MultiPolygon([orient(p, 1.0) for p in geom.geoms])
    else:
        geom = orient(geom, 1.0)
    gj = mapping(geom)

    def ring(r):
        return [[round(x, ndigits), round(y, ndigits)] for x, y in r]

    if gj["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in gj["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in p] for p in gj["coordinates"]]}


def regions_by_month(alerts: Alerts, state_dates, min_ha: float = 1.0, mask=None) -> list:
    """Confirmed alerts (a combine() result) -> regions by month of first detection, time-sorted.

    A region is an 8-connected group of confirmed pixels whose earliest confirmed date falls in the same calendar
    month, of at least min_ha hectares (pixel area). state_dates: acquisition dates of the month-end states that were
    read. A month's `first_date` is the first state dated in or after that month and `not_before` the state before it
    (None for the first state); `last_date` is the newest state. mask: optional bool grid, other pixels are ignored.
    """
    from pyproj import Geod, Transformer
    from rasterio import features
    from rasterio.transform import Affine
    from scipy import ndimage
    from shapely.geometry import shape
    import shapely
    from shapely.ops import unary_union

    states = sorted(state_dates)
    if not states:
        raise ValueError("state_dates is empty")
    conf = np.isin(alerts.status, CONFIRMED) & ~np.isnat(alerts.first_date)
    if mask is not None:
        conf &= mask
    months = alerts.first_date.astype("datetime64[M]")
    a, b, c, d, e, f = alerts.transform
    affine = Affine(a, b, c, d, e, f)
    tr = Transformer.from_crs(alerts.epsg, 4326, always_xy=True)
    geod = Geod(ellps="WGS84")
    min_px = min_ha / alerts.pixel_ha
    out = []
    for m in np.unique(months[conf]):
        month = str(m)
        labels, n = ndimage.label(conf & (months == m), structure=np.ones((3, 3)))
        sizes = np.bincount(labels.ravel(), minlength=n + 1)
        year, mon = int(month[:4]), int(month[5:])
        i_state = next((i for i, s in enumerate(states) if (s.year, s.month) >= (year, mon)), len(states) - 1)
        for lab in range(1, n + 1):
            if sizes[lab] < min_px - 1e-9:
                continue
            region = labels == lab
            geom = unary_union([shape(g) for g, _ in features.shapes(region.astype(np.uint8), mask=region,
                                                                     transform=affine, connectivity=8)])
            ll = shapely.transform(geom, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
            out.append(AlertRegion(month=month, polygon=to_geojson(ll), area_ha=abs(geod.geometry_area_perimeter(ll)[0]) / 1e4,
                                   pixels=int(sizes[lab]), first_date=states[i_state],
                                   not_before=states[i_state - 1] if i_state > 0 else None, last_date=states[-1]))
    return out
