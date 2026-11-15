"""Contact sheet of the Barcelona picture frames: about 12 radar frames across the years and 6 photos, dated.

    python explore/barcelona/frames_contact.py   ->  explore/barcelona/frames_contact.jpg
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "barcelona"
THUMB = 480
COLS = 3


def pick(frames, n):
    """n frames spread evenly over the list, first and last included."""
    if len(frames) <= n:
        return frames
    return [frames[round(i * (len(frames) - 1) / (n - 1))] for i in range(n)]


def main():
    doc = json.loads((SITE / "frames.json").read_text(encoding="utf-8"))
    sets = {s["id"]: s["frames"] for s in doc["sets"]}
    radar = [f for f in sets["radar"] if f["sensor"] == "Sentinel-1"]
    nisar = [f for f in sets["radar"] if f["sensor"] == "NISAR"]
    tiles = [("radar", f) for f in pick(radar, 9) + [nisar[0], nisar[len(nisar) // 2], nisar[-1]]]
    tiles += [("photo", f) for f in pick(sets.get("photo", []), 6)]
    images = []
    for kind, f in tiles:
        im = Image.open(SITE / f["url"]).convert("RGB")
        im = im.resize((THUMB, round(THUMB * im.height / im.width)))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 200, 14), fill=(0, 0, 0))
        d.text((3, 2), f"{f['date']} {f['sensor']}", fill=(255, 255, 255))
        images.append(im)
    th = images[0].height
    rows = -(-len(images) // COLS)
    sheet = Image.new("RGB", (COLS * (THUMB + 4), rows * (th + 4)), (30, 30, 30))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % COLS) * (THUMB + 4), (i // COLS) * (th + 4)))
    out = ROOT / "explore" / "barcelona" / "frames_contact.jpg"
    sheet.save(out, quality=85)
    print(out, sheet.size, len(images))


if __name__ == "__main__":
    main()
