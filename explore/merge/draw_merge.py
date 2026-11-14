"""Draw the merged (Muhos clear-cut) and the nested case from the E1 tests: python explore/merge/draw_merge.py"""
import sys
from datetime import date as D
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_merge import SITE, det, muhos, sq  # noqa: E402

from sarwatch.merge import merge_detections  # noqa: E402

COL = {"Optical alert": (230, 130, 20), "Sentinel-1": (40, 100, 200), "NISAR": (40, 160, 70)}
W = H = 520


def panel(dets, changes, title):
    img = Image.new("RGB", (W, H + 60), "white")
    dr = ImageDraw.Draw(img)
    xs = [v for d in dets for v in d.polygon.bounds[0::2]]
    ys = [v for d in dets for v in d.polygon.bounds[1::2]]
    x0, y0, s = min(xs), min(ys), max(max(xs) - min(xs), max(ys) - min(ys)) * 1.15

    def px(p):
        return [((x - x0 + s * 0.075) / s * W, H - (y - y0 + s * 0.075) / s * H) for x, y in p.exterior.coords]

    dr.text((8, 6), title, fill="black")
    for i, d in enumerate(dets):
        dr.polygon(px(d.polygon), outline=COL[d.source], width=3)
        dr.text((8, H + 4 + 14 * i), f"{d.source}{' (late start)' if d.late_start else ''}", fill=COL[d.source])
    for c in changes:
        for g in getattr(c.geometry, "geoms", [c.geometry]):
            pts = px(g)
            for a, b in zip(pts[::2], pts[1::2]):  # dashed outline
                dr.line([a, b], fill="black", width=2)
    for i, c in enumerate(changes):
        dr.text((W // 2, H + 4 + 14 * i), f"change {i + 1}: {c.confidence}, {c.when[:42]}", fill="black")
    return img


m = muhos()
big = det("Optical alert", "optical", sq(0, 0, 0.02, 0.04), D(2026, 6, 20), nb=D(2026, 6, 1))
small = det("Sentinel-1", "radar", sq(0.005, 0.005, 0.005, 0.008), D(2026, 6, 24), nb=D(2026, 6, 12), conf="low")
a = panel(m, merge_detections(m, SITE), "Merged: 3 detections -> 1 change (dashed = union)")
b = panel([big, small], merge_detections([big, small], SITE), "Nested: 2 changes, each cites the other")
out = Image.new("RGB", (2 * W + 10, H + 60), "white")
out.paste(a, (0, 0))
out.paste(b, (W + 10, 0))
out.save(Path(__file__).with_name("merge_cases.png"))
