"""Quick looks for tuning a large site (Barcelona): detection on the cached stack without the export, a picture of
the whole window with the regions coloured by first year, before / after zooms, and a table of the regions.

    PYTHONPATH=src python explore/barcelona/look.py s1 --out <dir> [--set threshold_db=4 --set persist=99]
    PYTHONPATH=src python explore/barcelona/look.py s1 --out <dir> --zoom 2.07,41.29,3 --zoom 2.16,41.35,2

Reads data/stacks/<site>/<sensor>/ only (offline). Pictures: false colour as the app's layers (red = co-pol, green =
cross-pol, blue = their ratio), regions filled with one colour per first year (S1) or month (NISAR).
"""
from __future__ import annotations

import argparse
import dataclasses
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer

from sarwatch import pipeline
from sarwatch.export import COLOUR_DB, _colour, _median_power

YEAR_COLOURS = {  # first year -> RGB, early = cold, late = warm
    2016: (90, 90, 255), 2017: (0, 160, 255), 2018: (0, 220, 220), 2019: (0, 220, 120), 2020: (120, 230, 0),
    2021: (220, 230, 0), 2022: (255, 200, 0), 2023: (255, 140, 0), 2024: (255, 80, 0), 2025: (255, 0, 80),
    2026: (255, 0, 200),
}


def detect(site_id: str, sensor: str, overrides: dict, cache: Path):
    site = pipeline.SITES[site_id]
    days = pipeline._in_season(site, sensor, pipeline.cached_days(cache / site_id / sensor))
    spans = pipeline._skip_spans(site)
    days = [d for d in days if not any(lo <= d <= hi for lo, hi in spans)]
    params = dataclasses.replace(pipeline._params(site, sensor), **overrides)
    return pipeline.detect(sensor, site, cache, days, params), params


def colour_of(region, sensor: str):
    if sensor == pipeline.S1:
        return YEAR_COLOURS.get(region.first_date.year, (255, 255, 255))
    month = region.first_date.month  # NISAR: Jun .. Nov
    return YEAR_COLOURS[2016 + min(10, 2 * max(0, month - 6))]


def picture(run, when: str, n: int = 3) -> np.ndarray:
    sl = slice(0, n) if when == "before" else slice(len(run.dates) - n, len(run.dates))
    power = {p: _median_power(a, sl) for p, a in run.stack.items()}
    with np.errstate(divide="ignore", invalid="ignore"):
        db = {p: 10 * np.log10(v) for p, v in power.items()}
    band = "C" if "VV" in run.stack else "L"
    return _colour(db, band)[..., :3]


def overlay(rgb: np.ndarray, run, sensor: str, alpha: float = 0.75) -> np.ndarray:
    out = rgb.astype(np.float32).copy()
    lut = np.zeros((len(run.result.regions) + 1, 3), np.float32)
    for r in run.result.regions:
        lut[r.label] = colour_of(r, sensor)
    lab = run.result.labels
    m = lab > 0
    out[m] = (1 - alpha) * out[m] + alpha * lut[lab[m]]
    return out.astype(np.uint8)


def keep_top(run, n: int):
    """The run with only its n largest regions (low confidence at half its area), labels renumbered."""
    weight = {"low": 0.5}
    order = sorted(run.result.regions, key=lambda r: -r.area_ha * weight.get(r.confidence, 1.0))[:n]
    keep = {r.label for r in order}
    remap = np.zeros(len(run.result.regions) + 1, dtype=run.result.labels.dtype)
    regions = []
    for r in run.result.regions:
        if r.label in keep:
            remap[r.label] = len(regions) + 1
            regions.append(dataclasses.replace(r, label=len(regions) + 1))
    result = dataclasses.replace(run.result, labels=remap[run.result.labels], regions=regions)
    return dataclasses.replace(run, result=result)


def lonlat_to_px(run, lon, lat):
    x, y = Transformer.from_crs(4326, run.epsg, always_xy=True).transform(lon, lat)
    a, b, c, d, e, f = run.transform
    return (y - f) / e, (x - c) / a


def centroid_lonlat(run, region):
    r0, c0, r1, c1 = region.bbox
    rows, cols = np.nonzero(run.result.labels[r0:r1, c0:c1] == region.label)
    a, b, c, d, e, f = run.transform
    x, y = a * (cols.mean() + c0 + 0.5) + c, e * (rows.mean() + r0 + 0.5) + f
    return Transformer.from_crs(run.epsg, 4326, always_xy=True).transform(x, y)


def table(run, top: int = 40) -> str:
    by = defaultdict(lambda: [0, 0.0])
    years = defaultdict(lambda: [0, 0.0])
    for r in run.result.regions:
        by[r.type][0] += 1
        by[r.type][1] += r.area_ha
        years[r.first_date.year if run.sensor.startswith("Sentinel") else r.first_date.isoformat()[:7]][0] += 1
        years[r.first_date.year if run.sensor.startswith("Sentinel") else r.first_date.isoformat()[:7]][1] += r.area_ha
    lines = [f"{len(run.result.regions)} regions, {sum(v[1] for v in by.values()):.0f} ha"]
    lines.append("by type: " + ", ".join(f"{k} {n} = {ha:.0f} ha" for k, (n, ha) in sorted(by.items())))
    lines.append("by first: " + ", ".join(f"{k} {n} = {ha:.0f} ha" for k, (n, ha) in sorted(years.items())))
    for r in sorted(run.result.regions, key=lambda r: -r.area_ha)[:top]:
        lon, lat = centroid_lonlat(run, r)
        s = r.signal
        lines.append(f"  {r.label:5d} {r.type:<10} {r.area_ha:7.1f} ha  {r.first_date}  {lat:.4f} N {lon:.4f} E  "
                     f"{s['metric']} {s['before']:.1f} -> {s['after']:.1f} ({s['delta']:+.1f})  {r.confidence}")
    return "\n".join(lines)


def zoom(run, sensor, lon, lat, km, path: Path, scale: int = 3) -> None:
    row, col = lonlat_to_px(run, lon, lat)
    px = abs(run.transform[0])
    half = int(km * 500 / px)
    r0, r1 = max(0, int(row) - half), int(row) + half
    c0, c1 = max(0, int(col) - half), int(col) + half
    before, after = picture(run, "before")[r0:r1, c0:c1], picture(run, "after")[r0:r1, c0:c1]
    marked = overlay(after, _Crop(run, r0, r1, c0, c1), sensor, alpha=0.45)
    gap = np.full((before.shape[0], 4, 3), 255, np.uint8)
    img = Image.fromarray(np.hstack([before, gap, after, gap, marked]))
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    ImageDraw.Draw(img).text((6, 4), f"{lat:.4f} N {lon:.4f} E  {km} km  before | after | regions", fill=(255, 255, 255))
    img.save(path)


@dataclasses.dataclass
class _Crop:
    """The bits of a run that overlay() needs, cut to a window."""
    run: object
    r0: int
    r1: int
    c0: int
    c1: int

    @property
    def result(self):
        return dataclasses.replace(self.run.result, labels=self.run.result.labels[self.r0:self.r1, self.c0:self.c1])


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("sensor", choices=(pipeline.S1, pipeline.NISAR))
    p.add_argument("--site", default="barcelona")
    p.add_argument("--out", required=True)
    p.add_argument("--cache", default=str(pipeline.REPO_ROOT / "data" / "stacks"))
    p.add_argument("--set", action="append", default=[], help="ChangeParams override, key=value")
    p.add_argument("--zoom", action="append", default=[], help="lon,lat,km")
    p.add_argument("--tag", default="")
    p.add_argument("--top", type=int, help="keep only the N largest regions (low confidence counted at half)")
    p.add_argument("--tiles", action="store_true", help="also write the window as 2 x 2 full-resolution tiles")
    args = p.parse_args(argv)
    overrides = {}
    for kv in args.set:
        k, v = kv.split("=", 1)
        overrides[k] = None if v == "None" else (v == "True" if v in ("True", "False") else
                                                  (int(v) if v.lstrip("-").isdigit() else
                                                   (float(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v)))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    run, params = detect(args.site, args.sensor, overrides, Path(args.cache))
    if args.top:
        run = keep_top(run, args.top)
    tag = f"{args.sensor}{args.tag}"
    text = table(run)
    (out / f"{tag}-regions.txt").write_text(f"{params}\n{text}\n", encoding="utf-8")
    print(text)
    over = overlay(picture(run, "after"), run, args.sensor)
    img = Image.fromarray(over)
    k = math.ceil(max(img.size) / 1400)
    img.resize((img.width // k, img.height // k), Image.LANCZOS).save(out / f"{tag}-overview.png")
    if args.tiles:
        h, w = over.shape[:2]
        for i, (r, c) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            tile = over[r * h // 2:(r + 1) * h // 2, c * w // 2:(c + 1) * w // 2]
            Image.fromarray(tile).save(out / f"{tag}-tile{i}.png")
    for z in args.zoom:
        lon, lat, km = (float(v) for v in z.split(","))
        zoom(run, args.sensor, lon, lat, km, out / f"{tag}-zoom-{lat:.3f}-{lon:.3f}.png")


if __name__ == "__main__":
    main()
