"""Port and airport land: is the change on land the urban plan qualifies as a port or airport system?

Service: the same Generalitat WFS as ``zoning`` (``sig.gencat.cat/ows/PLANEJAMENT/wfs``), layer
``PLANEJAMENT:MUC_QUALIFICACIONS`` (the qualification of each piece of land, MUC). ``SP`` = "Sistemes, Portuari",
``SA`` = "Sistemes, Aeroportuari". In MUC the port is often classed as non-buildable (SNU) although it is where
terminals, yards and quays are built, so the classification alone would flag ordinary port works.
"""
from __future__ import annotations

from shapely.geometry import shape

from ._common import safe, to_utm
from .zoning import VIEWER, features_in_box

SOURCE = "Mapa urbanístic de Catalunya (MUC), qualifications, Generalitat de Catalunya"
LAYER = "PLANEJAMENT:MUC_QUALIFICACIONS"
KINDS = {"SP": "port", "SA": "airport"}  # CODI_QUAL_MUC -> our label


@safe(SOURCE, VIEWER)
def lookup(geometry: dict, **options) -> dict:
    """``system`` ("port" | "airport" | None: the kind covering the largest share), ``shares`` ({kind: fraction of the
    polygon's area}) and ``classes`` (every raw qualification touched)."""
    g = to_utm(geometry)
    shares, classes = {}, set()
    for f in features_in_box(*g.bounds, layer=LAYER):
        a = shape(f["geometry"]).buffer(0).intersection(g).area
        if a <= 0:
            continue
        p = f["properties"]
        classes.add(str(p.get("DESC_QUAL_MUC")))
        kind = KINDS.get(p.get("CODI_QUAL_MUC"))
        if kind:
            shares[kind] = shares.get(kind, 0.0) + a / g.area
    system = max(shares, key=shares.get) if shares else None
    return {"system": system, "shares": {k: round(v, 3) for k, v in shares.items()}, "classes": sorted(classes)}
