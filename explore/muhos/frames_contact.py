"""Contact sheet of the Muhos picture frames: every 5th radar frame and all photos, dated, clearing outline on one.

    python explore/muhos/frames_contact.py   ->  explore/muhos/frames_contact.jpg
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "muhos"
THUMB = 230
COLS = 6


def outline_pixels(coords, size):
    (west, north), (east, _), _, (_, south) = coords
    w, h = size
    ring = json.loads((ROOT / "explore" / "muhos" / "clearing_scope.geojson").read_text(encoding="utf-8"))
    geom = ring["features"][0]["geometry"] if ring.get("type") == "FeatureCollection" else ring["geometry"]
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [[((x - west) / (east - west) * w, (north - y) / (north - south) * h) for x, y, *_ in poly[0]]
            for poly in polys]


def main():
    doc = json.loads((SITE / "frames.json").read_text(encoding="utf-8"))
    sets = {s["id"]: s["frames"] for s in doc["sets"]}
    tiles = [("radar", f) for f in sets["radar"][::5]] + [("photo", f) for f in sets["photo"]]
    first = True
    images = []
    for kind, f in tiles:
        im = Image.open(SITE / f["url"]).convert("RGB")
        im = im.resize((THUMB, round(THUMB * im.height / im.width)))
        d = ImageDraw.Draw(im)
        if first or (kind == "photo" and f is sets["photo"][-1]):
            for poly in outline_pixels(doc["coordinates"], im.size):
                d.line(poly, fill=(255, 40, 40), width=1)
            first = False
        d.rectangle((0, 0, 120, 14), fill=(0, 0, 0))
        d.text((3, 2), f"{kind} {f['date']}", fill=(255, 255, 255))
        images.append(im)
    th = images[0].height
    rows = -(-len(images) // COLS)
    sheet = Image.new("RGB", (COLS * (THUMB + 4), rows * (th + 4)), (30, 30, 30))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % COLS) * (THUMB + 4), (i // COLS) * (th + 4)))
    out = ROOT / "explore" / "muhos" / "frames_contact.jpg"
    sheet.save(out, quality=82)
    print(out, sheet.size, len(images))


if __name__ == "__main__":
    main()
