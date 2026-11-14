"""Solar-plant applications (Catalan open data, Socrata dataset ``ggx8-jkp4``): plants filed in the change's municipality.

The list locates plants by **municipality only** (no coordinates), so we find the municipality containing the
polygon's centre: point -> municipality comes from the municipal boundaries of the urban-planning map
(``PLANEJAMENT:MUC_AMBIT_MUNICIPAL``, same Generalitat WFS as ``zoning``), which carries the 5-digit INE code. The
dataset's ``codi_municipi`` is that INE code plus one check digit (e.g. Gelida 08091 -> 080910), so we match by prefix.
A plant spanning several municipalities has one row per municipality.
"""
from __future__ import annotations

import json

from shapely.geometry import shape

from ._common import fetch, safe, to_utm
from .zoning import features_in_box

SOURCE = "Solar PV plant applications (Generalitat de Catalunya open data, ggx8-jkp4)"
SERVICE = "https://analisi.transparenciacatalunya.cat/resource/ggx8-jkp4.json"
VIEWER = "https://analisi.transparenciacatalunya.cat/d/ggx8-jkp4"


def municipality_at(point) -> dict | None:
    """EPSG:25831 shapely point -> {code (INE, 5 digits), name}, or None outside Catalonia."""
    x, y = point.x, point.y
    for f in features_in_box(x - 1, y - 1, x + 1, y + 1, layer="PLANEJAMENT:MUC_AMBIT_MUNICIPAL"):
        if shape(f["geometry"]).buffer(0).covers(point):
            return {"code": f["properties"]["CODI_INE"], "name": f["properties"]["MUNICIPI"]}
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, **options) -> dict:
    """``municipality`` ({code, name} or None) and ``plants`` ([{name, status, ha, ha_in_municipality, mw,
    municipality, environmental_procedure}]) filed in that municipality."""
    muni = municipality_at(to_utm(geometry).centroid)
    if muni is None:
        return {"municipality": None, "plants": []}
    rows = json.loads(fetch("solar", SERVICE, {
        "$where": f"starts_with(codi_municipi, '{muni['code']}')", "$limit": 1000,
    }))
    plants = [{
        "name": r.get("nom"),
        "status": r.get("estat"),
        "ha": _num(r.get("superf_cie_ha")),
        "ha_in_municipality": _num(r.get("superf_cie_al_municipi_ha")),
        "mw": _num(r.get("pot_ncia_mw")),
        "municipality": r.get("municipi"),
        "environmental_procedure": r.get("tr_mit_ambiental"),
    } for r in rows if str(r.get("codi_municipi", ""))[:5] == muni["code"]]
    return {"municipality": muni, "plants": plants}
