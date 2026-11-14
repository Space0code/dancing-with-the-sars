"""Pictures and a diff for the Muhos review fixes (#27, PR #95 review): the cumulative-hectares curves from
app/data/muhos/story_series.json, and the clearing parts' outlines before (OLD, a folder with the old
changes.geojson, e.g. a copy of origin/main's app/data/muhos) and after smoothing.

    python explore/muhos/review_fixes_pictures.py <old muhos folder>
    # -> explore/muhos/review_fixes_curves.png, review_fixes_outlines.png; prints which fields changed per id
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "app" / "data" / "muhos"
COLORS = ["#1b7837", "#2166ac", "#b2182b"]


def feats(path):
    return {f["properties"]["id"]: f for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"]}


def main():
    old = feats(Path(sys.argv[1]) / "changes.geojson")
    new = feats(SITE / "changes.geojson")
    assert old.keys() == new.keys()
    print("ids equal:", len(new))
    for i, f in new.items():
        a, b = old[i]["properties"], f["properties"]
        diff = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        if diff:
            print(i, diff)
    data = json.loads((SITE / "story_series.json").read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for s, c in zip(data["series"], COLORS):
        ax.plot(s["dates"], s["values"], marker="o", ms=3, color=c, label=s["name"].split(", inside")[0])
    ticks = sorted({d for s in data["series"] for d in s["dates"]})
    ax.set_xticks(ticks[::3])
    ax.set_xticklabels(ticks[::3], rotation=60, fontsize=7)
    ax.set_ylabel("hectares inside the clearing outline (450 ha)")
    ax.set_title("Muhos: three sources, three separate lines (Sentinel-1 starts at its first 2026 pass)")
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(Path(__file__).with_name("review_fixes_curves.png"), dpi=110)
    fig, axes = plt.subplots(1, 2, figsize=(12, 7), sharex=True, sharey=True)
    parts = [i for i, f in new.items() if f["properties"]["sensor"] == "OPERA DIST-ALERT"
             and f["properties"]["area_ha"] > 3 and shape(f["geometry"]).centroid.within(
                 shape(json.loads((ROOT / "explore/muhos/clearing_scope.geojson").read_text())["geometry"]))]
    for ax, feat, title in ((axes[0], old, "before"), (axes[1], new, "after")):
        for k, i in enumerate(parts):
            g = shape(feat[i]["geometry"])
            for poly in getattr(g, "geoms", [g]):
                ax.fill(*poly.exterior.xy, alpha=0.55, color=plt.cm.viridis(k / max(1, len(parts) - 1)), lw=0.4,
                        ec="k")
                for r in poly.interiors:
                    ax.fill(*r.xy, color="white", lw=0.3, ec="k")
        ax.set_title(title)
        ax.set_aspect(1 / 0.43)
    fig.tight_layout()
    fig.savefig(Path(__file__).with_name("review_fixes_outlines.png"), dpi=110)


if __name__ == "__main__":
    main()
