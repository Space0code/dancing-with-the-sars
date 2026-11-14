"""Public-record lookups, run offline from the saved responses in tests/fixtures/context/.

Re-record the fixtures (needs network): delete the folder's files, then run this file with
``SARWATCH_LIVE=1 SARWATCH_RECORD=1``. ``SARWATCH_LIVE=1`` alone also runs the live smoke test.
"""
import math
import os
from pathlib import Path

import pytest
from shapely.geometry import box

from sarwatch import context
from sarwatch.context import _common, cadastre

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "context"
LIVE = os.environ.get("SARWATCH_LIVE") == "1"


def square(lon, lat, half_m):
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
            [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return {"type": "Polygon", "coordinates": [ring]}


AGROPARC = square(1.85, 41.45, 250)      # Agroparc Penedès, Gelida: ~500 m square
MONTSENY = square(2.43, 41.77, 50)       # inside Montseny (PEIN + Natura 2000 + natural park)
BARCELONA = square(2.1635, 41.3915, 50)  # Eixample blocks, central Barcelona


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(_common, "CACHE_DIR", FIXTURES)
    monkeypatch.setattr(_common, "OFFLINE", not (LIVE and os.environ.get("SARWATCH_RECORD") == "1"))


@pytest.fixture(scope="module")
def results():
    mp = pytest.MonkeyPatch()
    mp.setattr(_common, "CACHE_DIR", FIXTURES)
    mp.setattr(_common, "OFFLINE", not (LIVE and os.environ.get("SARWATCH_RECORD") == "1"))
    out = {name: context.lookup_all(g, since="2020-01-01")
           for name, g in {"agroparc": AGROPARC, "montseny": MONTSENY, "barcelona": BARCELONA}.items()}
    mp.undo()
    return out


@pytest.mark.parametrize("place", ["agroparc", "montseny", "barcelona"])
def test_every_lookup_answers_with_the_common_fields(results, place):
    for name, r in results[place].items():
        assert r["checked"], (name, r.get("error"))
        assert r["source"] and r["url"].startswith("https://")
        assert "error" not in r


def test_protected(results):
    assert results["agroparc"]["protected"]["inside"] is False
    assert results["barcelona"]["protected"]["inside"] is False
    m = results["montseny"]["protected"]
    assert m["inside"] is True
    kinds = {a["kind"] for a in m["areas"]}
    assert {"PEIN", "Natura 2000 SAC", "natural park"} <= kinds
    assert m["url"].startswith("https://natura2000.eea.europa.eu/")


def test_cadastre(results):
    b = results["barcelona"]["cadastre"]
    assert b["buildings"] > 10 and b["newest_date"][:4].isdigit() and b["built_since"] == 0
    assert results["montseny"]["cadastre"]["buildings"] == 0
    assert results["montseny"]["cadastre"]["newest_date"] is None
    assert results["agroparc"]["cadastre"]["buildings"] >= 1


def test_zoning(results):
    assert results["agroparc"]["zoning"]["zone"] == "non_buildable"
    assert results["agroparc"]["zoning"]["class"] == "Sòl no urbanitzable"
    assert results["montseny"]["zoning"]["zone"] == "non_buildable"
    assert results["barcelona"]["zoning"]["zone"] == "urban"
    assert abs(sum(results["barcelona"]["zoning"]["shares"].values()) - 1) < 0.01


def test_solar(results):
    a = results["agroparc"]["solar"]
    assert a["municipality"] == {"code": "08091", "name": "Gelida"}
    assert all(p["municipality"] == "Gelida" for p in a["plants"]) and a["plants"]
    assert set(a["plants"][0]) >= {"name", "status", "ha", "municipality"}
    assert results["barcelona"]["solar"]["municipality"]["name"] == "Barcelona"


@pytest.mark.parametrize("fn", list(context.LOOKUPS.values()))
def test_never_raises(fn, monkeypatch, tmp_path):
    monkeypatch.setattr(_common, "OFFLINE", True)       # also in re-record mode: the last square must stay a miss
    monkeypatch.setattr(_common, "CACHE_DIR", tmp_path)
    for bad in ({"type": "Point", "coordinates": [1.85, 41.45]}, None, square(1.0, 41.0, 100)):  # last: not cached
        r = fn(bad)
        assert r["checked"] is False and r["error"] and r["source"] and r["url"]


def test_cadastre_tiles_stay_under_the_4km2_limit(monkeypatch):
    boxes = []
    empty = b'<?xml version="1.0"?><gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml/3.2"/>'

    def fake(source, url, params, **kw):
        boxes.append([float(v) for v in params["bbox"].split(",")])
        return empty

    monkeypatch.setattr(cadastre, "fetch", fake)
    r = cadastre.lookup(square(1.85, 41.45, 2600))  # 5.2 km square, 27 km²
    assert r["checked"] and r["buildings"] == 0
    assert len(boxes) == 9
    assert all((x1 - x0) * (y1 - y0) <= 4e6 for x0, y0, x1, y1 in boxes)


def test_cadastre_since_compares_years(monkeypatch):
    parsed = [{"id": "a", "date": "2021-01-01", "parts": []}, {"id": "b", "date": "1990-01-01", "parts": []}]
    monkeypatch.setattr(cadastre, "_tile", lambda *b: [dict(f, parts=[box(*b)]) for f in parsed])
    r = cadastre.lookup(BARCELONA, since="2021-06-30")
    assert (r["buildings"], r["newest_date"], r["built_since"]) == (2, "2021-01-01", 1)


@pytest.mark.skipif(not LIVE, reason="set SARWATCH_LIVE=1 to hit the real services")
def test_live_smoke(monkeypatch, tmp_path):
    monkeypatch.setattr(_common, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(_common, "OFFLINE", False)
    r = context.lookup_all(AGROPARC, since="2020-01-01")
    assert all(v["checked"] for v in r.values()), {k: v.get("error") for k, v in r.items()}
