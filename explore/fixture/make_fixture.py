"""Generate app/data/fixture/: a FAKE but contract-valid site near Gelida.

It exists so the web app and the verdict step can be built before real radar
results arrive. Nothing in it is a real detection. Standard library only.

    python explore/fixture/make_fixture.py        # rerunnable, deterministic
"""
from __future__ import annotations

import json
import math
import random
import struct
import zlib
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "app" / "data" / "fixture"
SITE = "fixture"
WEST, SOUTH, EAST, NORTH = 1.80, 41.42, 1.90, 41.48
W, H = 320, 240  # site picture size in pixels
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians((SOUTH + NORTH) / 2))

NISAR_DATES = [date(2026, 6, 23) + timedelta(days=12 * i) for i in range(12)]
S1_DATES = [date(2024 + m // 12, m % 12 + 1, 15) for m in range(34)]  # Jan 2024 .. Oct 2026
BEFORE_DATE, AFTER_DATE = "2024-01-15", "2026-11-02"  # dates of the two site pictures

# type -> (HH change, HV change) in dB once the change has happened
EFFECT_DB = {
    "clearing": (-1.0, -6.0),
    "structure": (8.0, 1.0),
    "earthworks": (4.0, -3.0),
    "fire": (-0.5, -4.0),
}

R_PROTECTED = {"code": "protected_area", "text": "Inside a protected natural area.",
               "source": "PEIN / Natura 2000 (fake example)", "url": None, "effect": "raises"}
R_NONBUILD = {"code": "zoning_non_buildable", "text": "The land is zoned as non-buildable.",
              "source": "Urban-planning map (fake example)", "url": None, "effect": "raises"}
R_NORECORD = {"code": "no_record_found", "text": "No building, permit or planned project is on record here.",
              "source": "Land registry (fake example)", "url": "https://www.sedecatastro.gob.es/", "effect": "raises"}
R_SECTOR = {"code": "planned_sector", "text": "Inside a planned development sector.",
            "source": "Urban-planning map (fake example)", "url": None, "effect": "lowers"}
R_BUILDING = {"code": "cadastre_building_found", "text": "A new building is registered here.",
              "source": "Land registry (fake example)", "url": "https://www.sedecatastro.gob.es/", "effect": "lowers"}
R_FIRE = {"code": "fire_recorded", "text": "A wildfire was recorded here on the same dates.",
          "source": "NASA FIRMS (fake example)", "url": "https://firms.modaps.eosdis.nasa.gov/", "effect": "lowers"}
R_SMALL = {"code": "small_area", "text": "The change is small and the signal is weak.",
           "source": "Radar measurement (fake example)", "url": None, "effect": "neutral"}

# id, type, first, last, sensor, confidence, verdict, reasons, centre (lon, lat), outline offsets in metres
CHANGES = [
    (1, "earthworks", "2025-03-15", "2026-09-15", "Sentinel-1 C-band", "high", "review", [R_NONBUILD, R_NORECORD],
     (1.842, 41.452), [(-420, -260), (380, -330), (520, 60), (250, 330), (-300, 280), (-520, 40)]),
    (2, "structure", "2026-07-17", "2026-07-29", "NISAR L-band", "high", "expected", [R_SECTOR, R_BUILDING],
     (1.868, 41.441), [(-90, -80), (100, -90), (110, 70), (-80, 90)]),
    (3, "clearing", "2026-08-10", "2026-09-03", "NISAR L-band", "high", "high_concern", [R_PROTECTED, R_NORECORD],
     (1.822, 41.468), [(-220, -150), (160, -200), (260, 40), (90, 220), (-240, 130)]),
    (4, "clearing", "2026-06-23", "2026-06-23", "NISAR L-band", "low", "review", [R_NONBUILD, R_SMALL],
     (1.885, 41.463), [(-60, -50), (55, -60), (70, 45), (-50, 55)]),
    (5, "fire", "2025-07-15", "2025-07-15", "Sentinel-1 C-band", "medium", "expected", [R_FIRE],
     (1.815, 41.432), [(-450, -300), (300, -380), (520, -40), (380, 330), (-150, 400), (-520, 120)]),
    (6, "earthworks", "2026-10-09", "2026-11-02", "NISAR L-band", "medium", "review", [R_NONBUILD, R_NORECORD],
     (1.858, 41.472), [(-150, -110), (140, -130), (170, 90), (-20, 150), (-170, 60)]),
    (7, "structure", "2024-05-15", "2024-08-15", "Sentinel-1 C-band", "medium", "expected", [R_SECTOR, R_BUILDING],
     (1.878, 41.428), [(-70, -70), (80, -75), (85, 65), (-65, 70)]),
]

EXPLAIN = {
    "clearing": "Radar saw the tree signal drop by {d:.0f} dB here, the pattern left when forest is cut.",
    "structure": "Radar saw a strong new echo here ({d:+.0f} dB), the pattern of walls or metal structures.",
    "earthworks": "The surface here kept changing between satellite passes, the pattern of moving earth.",
    "fire": "Radar saw the tree signal drop by {d:.0f} dB here, matching a recorded wildfire.",
}


def ring(centre, offsets):
    lon0, lat0 = centre
    pts = [[round(lon0 + dx / M_PER_DEG_LON, 6), round(lat0 + dy / M_PER_DEG_LAT, 6)] for dx, dy in offsets]
    return pts + [pts[0]]


def area_ha(offsets):
    n = len(offsets)
    twice = sum(offsets[i][0] * offsets[(i + 1) % n][1] - offsets[(i + 1) % n][0] * offsets[i][1] for i in range(n))
    return round(abs(twice) / 2 / 10_000, 1)


def inside(lon, lat, poly):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def write_png(path: Path, rows) -> None:
    """rows: list of rows, each a list of (r, g, b) 0..255."""
    height, width = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def colour(hh_db, hv_db):
    """Common radar false colour: red = HH, green = HV, blue = HH minus HV."""
    def scale(v, lo, hi):
        return max(0, min(255, int(255 * (v - lo) / (hi - lo))))
    return scale(hh_db, -20, 0), scale(hv_db, -26, -6), scale(hh_db - hv_db, 0, 16)


def crop(img, poly, margin=12, zoom=3):
    xs = [(lon - WEST) / (EAST - WEST) * W for lon, _ in poly]
    ys = [(NORTH - lat) / (NORTH - SOUTH) * H for _, lat in poly]
    x0, x1 = max(0, int(min(xs)) - margin), min(W, int(max(xs)) + margin)
    y0, y1 = max(0, int(min(ys)) - margin), min(H, int(max(ys)) + margin)
    out = []
    for y in range(y0, y1):
        row = [px for px in img[y][x0:x1] for _ in range(zoom)]
        out.extend([row] * zoom)
    return out


def series_values(dates, first, base, delta, rng):
    return [round(base + (delta if d.isoformat() >= first else 0.0) + rng.uniform(-0.6, 0.6), 2) for d in dates]


def main() -> None:
    rng = random.Random(7)
    polys = {c[0]: ring(c[8], c[9]) for c in CHANGES}
    before, after = [], []
    for y in range(H):
        lat = NORTH - (y + 0.5) / H * (NORTH - SOUTH)
        row_b, row_a = [], []
        for x in range(W):
            lon = WEST + (x + 0.5) / W * (EAST - WEST)
            speckle = 10 * math.log10(rng.gammavariate(12, 1 / 12))
            hh, hv = -8.0 + speckle, -14.0 + speckle
            row_b.append(colour(hh, hv))
            for num, kind, *_ in CHANGES:
                if inside(lon, lat, polys[num]):
                    hh, hv = hh + EFFECT_DB[kind][0], hv + EFFECT_DB[kind][1]
            row_a.append(colour(hh, hv))
        before.append(row_b)
        after.append(row_a)
    write_png(OUT / "layers" / "radar_before.png", before)
    write_png(OUT / "layers" / "radar_after.png", after)

    corners = [[WEST, NORTH], [EAST, NORTH], [EAST, SOUTH], [WEST, SOUTH]]
    layers = {"layers": [
        {"id": "radar_before", "title": "Radar picture before", "date": BEFORE_DATE, "url": "layers/radar_before.png",
         "coordinates": corners, "caption": "Fake radar picture. Red = surface echo (HH), green = vegetation echo (HV)."},
        {"id": "radar_after", "title": "Radar picture after", "date": AFTER_DATE, "url": "layers/radar_after.png",
         "coordinates": corners, "caption": "Fake radar picture after the changes."},
    ]}
    (OUT / "layers.json").write_text(json.dumps(layers, indent=1), encoding="utf-8")

    features = []
    for num, kind, first, last, sensor, confidence, verdict, reasons, centre, offsets in CHANGES:
        cid = f"{SITE}-{num:04d}"
        d_hh, d_hv = EFFECT_DB[kind]
        metric, base, delta = ("HH_dB", -8.0, d_hh) if kind == "structure" else ("HV_dB", -14.0, d_hv)
        if sensor.startswith("Sentinel"):
            metric = metric.replace("HH", "VV").replace("HV", "VH")
        write_png(OUT / "evidence" / f"{cid}_before.png", crop(before, polys[num]))
        write_png(OUT / "evidence" / f"{cid}_after.png", crop(after, polys[num]))
        series = {"series": [
            {"name": "Vegetation echo (VH)", "unit": "dB", "sensor": "Sentinel-1 C-band",
             "dates": [d.isoformat() for d in S1_DATES], "values": series_values(S1_DATES, first, -15.0, d_hv, rng)},
            {"name": "Surface echo (VV)", "unit": "dB", "sensor": "Sentinel-1 C-band",
             "dates": [d.isoformat() for d in S1_DATES], "values": series_values(S1_DATES, first, -9.0, d_hh, rng)},
            {"name": "Vegetation echo (HV)", "unit": "dB", "sensor": "NISAR L-band",
             "dates": [d.isoformat() for d in NISAR_DATES], "values": series_values(NISAR_DATES, first, -14.0, d_hv, rng)},
            {"name": "Surface echo (HH)", "unit": "dB", "sensor": "NISAR L-band",
             "dates": [d.isoformat() for d in NISAR_DATES], "values": series_values(NISAR_DATES, first, -8.0, d_hh, rng)},
        ], "events": [{"date": first, "label": "Change first seen"}]}
        (OUT / "series").mkdir(parents=True, exist_ok=True)
        (OUT / "series" / f"{cid}.json").write_text(json.dumps(series, indent=1), encoding="utf-8")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [polys[num]]},
            "properties": {
                "id": cid, "site": SITE, "type": kind, "first_date": first, "last_date": last,
                "area_ha": area_ha(offsets), "sensor": sensor,
                "signal": {"metric": metric, "before": base, "after": round(base + delta, 1), "delta": delta},
                "confidence": confidence, "verdict": verdict, "reasons": reasons,
                "explain": EXPLAIN[kind].format(d=delta),
                "evidence": {"before": f"evidence/{cid}_before.png", "after": f"evidence/{cid}_after.png",
                             "series": f"series/{cid}.json", "before_date": BEFORE_DATE, "after_date": AFTER_DATE},
            },
        })
    collection = {"type": "FeatureCollection", "features": features}
    (OUT / "changes.geojson").write_text(json.dumps(collection, indent=1), encoding="utf-8")

    story = {
        "headline": "Fake example site (for building the app)",
        "story": [
            "Nothing here is real. This site exists so the app and the verdict rules can be built and tested.",
            "It contains one change of every kind and every verdict, spread over three years.",
        ],
        "events": [{"date": "2025-07-01", "label": "A court pauses the works (fake)"}],
        "sources": [{"title": "Hand-off contract", "url": "https://github.com/Space0code/dancing-with-the-sars"}],
    }
    (OUT / "story.json").write_text(json.dumps(story, indent=1), encoding="utf-8")
    print(f"wrote {len(features)} fake changes to {OUT}")


if __name__ == "__main__":
    main()
