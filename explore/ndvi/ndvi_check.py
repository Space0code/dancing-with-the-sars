"""Sanity picture: NDVI curves of three Muhos changes with their first dates, plus the table of all changes.

    python explore/ndvi/ndvi_check.py   ->  explore/ndvi/ndvi-check.png  (and the table on stdout)
"""
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "muhos"
SHOW = ["muhos-0001", "muhos-0012", "muhos-0017"]


def main():
    changes = {f["properties"]["id"]: f["properties"]
               for f in json.loads((SITE / "changes.geojson").read_text(encoding="utf-8"))["features"]}
    print("id            area_ha  before  after  snow  water  dates")
    for cid, p in changes.items():
        s = json.loads((SITE / "series" / f"{cid}.json").read_text(encoding="utf-8"))
        n, sf = s.get("ndvi"), s["surface"]
        print(f"{cid}  {p['area_ha']:7.1f}  {n and n['before']!s:>6}  {n and n['after']!s:>5}  "
              f"{sf['snow_share']!s:>4}  {sf['water_share']!s:>5}  {n and len(n['dates'])}")
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for ax, cid in zip(axes, SHOW):
        p = changes[cid]
        n = json.loads((SITE / "series" / f"{cid}.json").read_text(encoding="utf-8"))["ndvi"]
        ax.plot([date.fromisoformat(d) for d in n["dates"]], n["values"], "o-", color="#2a7f3f", ms=4)
        ax.axvline(date.fromisoformat(p["first_date"]), color="#c0392b", ls="--", label="change first seen")
        ax.set_title(f"{cid} ({p['area_ha']:.0f} ha)", fontsize=10)
        ax.set_ylim(-0.1, 1)
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("NDVI (mean in polygon)")
    axes[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("NDVI from NASA HLS, Muhos: it falls after the clearing; winter snow dates are left out", fontsize=11)
    fig.tight_layout()
    fig.savefig(Path(__file__).with_name("ndvi-check.png"), dpi=110)


if __name__ == "__main__":
    main()
