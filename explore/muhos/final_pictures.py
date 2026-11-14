"""Pictures for the final Muhos data (#27): the clearing by date, a radar before / after pair, the cleared-hectares curve.

    python explore/muhos/final_pictures.py   # reads app/data/muhos/, writes explore/muhos/final_*.png

Background: the site's Sentinel-1 composites from layers.json (2025 summer before, Sep-Oct 2026 after). The
clearing's changes are filled by month of first detection; every other change is outlined in white. The curve is
app/data/muhos/story_series.json. Needs only Pillow and the committed app data.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "muhos"
OUT = Path(__file__).resolve().parent
RAMP = ["#440154", "#443983", "#31688e", "#21918c", "#35b779", "#90d743", "#fde725"]  # dark = early
INK, PANEL = "#1f1f1d", "#fcfcfb"
K = 3  # screen pixels per 30 m pixel
FONT, SMALL, BOLD = (ImageFont.load_default(size=s) for s in (15, 13, 19))


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def layer(name):
    meta = next(m for m in json.loads((SITE / "layers.json").read_text())["layers"] if m["id"] == name)
    img = Image.open(SITE / meta["url"]).convert("RGB")
    (tl, tr, br, bl) = meta["coordinates"]
    w, h = img.size
    # lon/lat -> pixel, affine from three corners (the Sentinel-1 grid is UTM: nearly north-up at this scale)
    src = np.array([[tl[0], tl[1], 1], [tr[0], tr[1], 1], [bl[0], bl[1], 1]])
    dst = np.array([[0, 0], [w, 0], [0, h]], float)
    m = np.linalg.solve(src, dst)
    return img, meta, lambda lon, lat: tuple(np.array([lon, lat, 1.0]) @ m)


def rings(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [ring for poly in polys for ring in poly[:1]]


def crop_box(to_px, scope, pad=40):
    xs, ys = zip(*(to_px(*p) for p in scope["coordinates"][0]))
    return int(min(xs)) - pad, int(min(ys)) - pad, int(max(xs)) + pad, int(max(ys)) + pad


def zoom(img, box):
    c = img.crop(box)
    return c.resize((c.width * K, c.height * K), Image.NEAREST)


def growth_map(changes, scope):
    img, meta, to_px = layer("sentinel_1_c_band_after")
    box = crop_box(to_px, scope)
    base = zoom(img, box).convert("RGBA")
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    part = [f for f in changes if f["properties"]["sensor"] == "OPERA DIST-ALERT" and _inside(f, scope)]
    months = sorted({f["properties"]["first_date"] for f in part})
    colour = {m: rgb(RAMP[round(i * (len(RAMP) - 1) / max(len(months) - 1, 1))]) for i, m in enumerate(months)}

    def px(p):
        x, y = to_px(*p)
        return (x - box[0]) * K, (y - box[1]) * K

    for f in part:
        for ring in rings(f["geometry"]):
            d.polygon([px(p) for p in ring], fill=colour[f["properties"]["first_date"]] + (215,))
    for f in changes:
        if f not in part:
            for ring in rings(f["geometry"]):
                d.line([px(p) for p in ring], fill=(255, 255, 255, 255), width=2)
    d.line([px(p) for p in scope["coordinates"][0]], fill=(255, 221, 0, 255), width=2)
    base = Image.alpha_composite(base, over).convert("RGB")

    margin, legend_w, title_h, foot_h = 16, 300, 56, 40
    out = Image.new("RGB", (base.width + legend_w + 3 * margin, base.height + title_h + foot_h), rgb(PANEL))
    out.paste(base, (margin, title_h))
    d = ImageDraw.Draw(out)
    d.text((margin, 10), "Muhos: the clearing by date (one change per month)", fill=rgb(INK), font=BOLD)
    d.text((margin, 34), "Fill = month the optical alerts first confirmed the loss; yellow = clearing outline; "
                         "white = other changes", fill=rgb(INK), font=SMALL)
    lx, ly = base.width + 2 * margin, title_h
    d.text((lx, ly), "First seen (state of)       ha    cum.", fill=rgb(INK), font=FONT)
    ly += 26
    cum = 0.0
    for m in months:
        ha = sum(f["properties"]["area_ha"] for f in part if f["properties"]["first_date"] == m)
        cum += ha
        d.rectangle([lx, ly, lx + 22, ly + 16], fill=colour[m])
        d.text((lx + 32, ly), f"{date.fromisoformat(m):%d %b %Y}", fill=rgb(INK), font=FONT)
        d.text((lx + 150, ly), f"{ha:6.1f}  {cum:6.1f}", fill=rgb(INK), font=FONT)
        ly += 24
    d.text((margin, title_h + base.height + 10), f"Background: Sentinel-1 radar, {meta['caption']}"[:150],
           fill=rgb(INK), font=SMALL)
    out.save(OUT / "final_growth_by_date.png", optimize=True)


def _inside(f, scope):
    from shapely.geometry import shape

    g = shape(f["geometry"])
    return g.intersection(shape(scope)).area >= 0.5 * g.area


def before_after(scope):
    tiles = []
    for name in ("sentinel_1_c_band_before", "sentinel_1_c_band_after"):
        img, meta, to_px = layer(name)
        box = crop_box(to_px, scope)
        z = zoom(img, box)
        d = ImageDraw.Draw(z)
        d.line([((to_px(*p)[0] - box[0]) * K, (to_px(*p)[1] - box[1]) * K) for p in scope["coordinates"][0]],
               fill=(255, 221, 0), width=2)
        tiles.append((z, f"{meta['title']} ({meta['caption'].split('.')[0]})"))
    margin, title_h, cap_h = 16, 56, 26
    w = sum(t.width for t, _ in tiles) + 3 * margin
    out = Image.new("RGB", (w, tiles[0][0].height + title_h + cap_h + margin), rgb(PANEL))
    d = ImageDraw.Draw(out)
    d.text((margin, 10), "Muhos clearing: Sentinel-1 radar before and after", fill=rgb(INK), font=BOLD)
    d.text((margin, 34), "Yellow-green = trees, purple-blue = bare ground; yellow line = clearing outline (optical "
                         "alerts)", fill=rgb(INK), font=SMALL)
    x = margin
    for t, cap in tiles:
        out.paste(t, (x, title_h))
        d.text((x, title_h + t.height + 6), cap, fill=rgb(INK), font=SMALL)
        x += t.width + margin
    out.save(OUT / "final_before_after.png", optimize=True)


def curve():
    doc = json.loads((SITE / "story_series.json").read_text())
    series = doc["series"]
    w, h, left, right, top, bottom = 900, 420, 70, 230, 50, 50
    out = Image.new("RGB", (w, h), rgb(PANEL))
    d = ImageDraw.Draw(out)
    d0 = date(2025, 9, 1).toordinal()
    d1 = date(2026, 11, 1).toordinal()
    vmax = 400

    def xy(day, v):
        return (left + (date.fromisoformat(day).toordinal() - d0) / (d1 - d0) * (w - left - right),
                h - bottom - v / vmax * (h - top - bottom))

    d.text((left, 12), "Muhos: cleared hectares inside the clearing outline, by source", fill=rgb(INK), font=BOLD)
    for v in range(0, vmax + 1, 100):
        y = xy("2025-09-01", v)[1]
        d.line([(left, y), (w - right, y)], fill=(225, 225, 222))
        d.text((left - 40, y - 8), f"{v}", fill=rgb(INK), font=SMALL)
    for m in ("2025-10-01", "2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"):
        x = xy(m, 0)[0]
        d.line([(x, h - bottom), (x, h - bottom + 5)], fill=rgb(INK))
        d.text((x - 20, h - bottom + 8), f"{date.fromisoformat(m):%b %Y}", fill=rgb(INK), font=SMALL)
    colours = ["#2a6fdb", "#e0661c", "#1a9e5a"]
    for s, c in zip(series, colours):
        pts = [xy(day, v) for day, v in zip(s["dates"], s["values"]) if v is not None]
        if len(pts) > 1:
            d.line(pts, fill=rgb(c), width=3)
        for p in pts:
            d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=rgb(c))
    ly = top
    for s, c in zip(series, colours):
        d.rectangle([w - right + 16, ly + 4, w - right + 34, ly + 14], fill=rgb(c))
        d.multiline_text((w - right + 40, ly), s["name"].replace(", ", ",\n"), fill=rgb(INK), font=SMALL)
        ly += 54
    for e in doc.get("events", []):
        x = xy(e["date"], 0)[0]
        d.line([(x, top), (x, h - bottom)], fill=(160, 160, 160))
    out.save(OUT / "final_hectares_curve.png", optimize=True)


def main():
    changes = json.loads((SITE / "changes.geojson").read_text(encoding="utf-8"))["features"]
    scope = json.loads((OUT / "clearing_scope.geojson").read_text())["geometry"]
    growth_map(changes, scope)
    before_after(scope)
    if (SITE / "story_series.json").is_file():
        curve()
    print("wrote explore/muhos/final_growth_by_date.png, final_before_after.png, final_hectares_curve.png")


if __name__ == "__main__":
    main()
