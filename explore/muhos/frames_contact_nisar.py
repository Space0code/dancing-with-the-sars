"""Contact sheet of the radar set: the last three Sentinel-1 frames and every NISAR frame, dated, clearing outline
thin on the last one.

    python explore/muhos/frames_contact_nisar.py   ->  explore/muhos/frames_contact_nisar.jpg
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from frames_contact import COLS, ROOT, SITE, outline_pixels

THUMB = 300


def main():
    doc = json.loads((SITE / "frames.json").read_text(encoding="utf-8"))
    radar = next(s["frames"] for s in doc["sets"] if s["id"] == "radar")
    s1 = [f for f in radar if f["sensor"] == "Sentinel-1"][-3:]
    tiles = s1 + [f for f in radar if f["sensor"] == "NISAR"]
    images = []
    for f in tiles:
        im = Image.open(SITE / f["url"]).convert("RGB")
        im = im.resize((THUMB, round(THUMB * im.height / im.width)))
        d = ImageDraw.Draw(im)
        if f is tiles[-1]:
            for poly in outline_pixels(doc["coordinates"], im.size):
                d.line(poly, fill=(40, 200, 255), width=1)
        d.rectangle((0, 0, 150, 14), fill=(0, 0, 0))
        d.text((3, 2), f"{f['sensor']} {f['date']}", fill=(255, 255, 255))
        images.append(im)
    th = images[0].height
    rows = -(-len(images) // COLS)
    sheet = Image.new("RGB", (COLS * (THUMB + 4), rows * (th + 4)), (30, 30, 30))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % COLS) * (THUMB + 4), (i // COLS) * (th + 4)))
    out = ROOT / "explore" / "muhos" / "frames_contact_nisar.jpg"
    sheet.save(out, quality=85)
    print(out, sheet.size, len(images))


if __name__ == "__main__":
    main()
