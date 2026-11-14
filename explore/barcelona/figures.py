"""Pictures of the exported Barcelona site for the PR and for humans who check it by looking.

    python explore/barcelona/figures.py                       # overview.jpg
    python explore/barcelona/figures.py 0010 0060 0057        # + zoom-<id>.jpg per change: before | after

Reads app/data/barcelona/ only (no radar cache): the Sentinel-1 "after" site picture with every change outlined and
filled in the colour of its first year, and the card pictures (evidence/) side by side with one line of facts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "barcelona"
OUT = Path(__file__).resolve().parent
YEAR_COLOURS = {
    2016: (90, 90, 255), 2017: (0, 160, 255), 2018: (0, 220, 220), 2019: (0, 220, 120), 2020: (120, 230, 0),
    2021: (220, 230, 0), 2022: (255, 200, 0), 2023: (255, 140, 0), 2024: (255, 80, 0), 2025: (255, 0, 80),
    2026: (255, 0, 200),
}


def changes() -> list:
    return json.loads((SITE / "changes.geojson").read_text(encoding="utf-8"))["features"]


def overview(path: Path, width: int = 1400) -> None:
    layer = next(x for x in json.loads((SITE / "layers.json").read_text(encoding="utf-8"))["layers"]
                 if x["id"] == "sentinel_1_c_band_after")
    img = Image.open(SITE / layer["url"]).convert("RGB")
    to_utm = Transformer.from_crs(4326, 32631, always_xy=True)
    (x0, y0), (x1, y1) = (to_utm.transform(*layer["coordinates"][i]) for i in (0, 2))  # north-up UTM grid
    sx, sy = img.width / (x1 - x0), img.height / (y1 - y0)
    grey = np.asarray(img.convert("L"), dtype=np.float32)
    base = Image.fromarray((np.dstack([grey] * 3) * 0.75).astype(np.uint8))  # grey, so the year colours stand out
    fill = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(fill)
    for f in changes():
        p = f["properties"]
        colour = YEAR_COLOURS[int(p["first_date"][:4])]
        geom = shape(f["geometry"])
        for poly in getattr(geom, "geoms", [geom]):
            xs, ys = to_utm.transform(*np.asarray(poly.exterior.coords).T)
            pts = list(zip((np.asarray(xs) - x0) * sx, (np.asarray(ys) - y0) * sy))
            draw.polygon(pts, fill=colour + (200,), outline=colour + (255,))
            cx, cy = np.mean(pts, axis=0)
            r = 9  # a ring around every change, so small ones show at this scale
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour + (255,), width=2)
    out = Image.alpha_composite(base.convert("RGBA"), fill).convert("RGB")
    legend = ImageDraw.Draw(out)
    for i, (year, colour) in enumerate(YEAR_COLOURS.items()):
        y = 12 + 22 * i
        legend.rectangle((12, y, 30, y + 16), fill=colour)
        legend.text((36, y + 2), f"first seen {year}", fill=(255, 255, 255))
    out = out.resize((width, round(out.height * width / out.width)), Image.LANCZOS)
    out.save(path, quality=85)


def zoom(cid: str, path: Path) -> None:
    f = next(x for x in changes() if x["properties"]["id"].endswith(cid))
    p = f["properties"]
    before, after = (Image.open(SITE / p["evidence"][k]).convert("RGB") for k in ("before", "after"))
    c = shape(f["geometry"]).centroid
    gap = 6
    out = Image.new("RGB", (before.width + after.width + gap, before.height + 34), (255, 255, 255))
    out.paste(before, (0, 34))
    out.paste(after, (before.width + gap, 34))
    draw = ImageDraw.Draw(out)
    draw.text((4, 3), f"{p['id']}  {p['type']}  {p['area_ha']:.1f} ha  first seen {p['first_date']}  "
                      f"{c.y:.4f} N {c.x:.4f} E", fill=(0, 0, 0))
    draw.text((4, 18), f"left: before ({p['evidence']['before_date']})   right: after ({p['evidence']['after_date']})",
              fill=(0, 0, 0))
    out.save(path, quality=90)


if __name__ == "__main__":
    overview(OUT / "overview.jpg")
    for cid in sys.argv[1:]:
        zoom(cid, OUT / f"zoom-{cid}.jpg")
