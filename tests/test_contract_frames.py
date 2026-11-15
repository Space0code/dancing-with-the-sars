"""frames.json and the site `hidden` flag in the data contract."""
import copy as _copy
import json
import shutil
from pathlib import Path

import pytest

from sarwatch.contract import validate

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
CORNERS = [[26.02, 64.875], [26.20, 64.875], [26.20, 64.795], [26.02, 64.795]]
GOOD = {"coordinates": CORNERS, "sets": [
    {"id": "radar", "title": "Radar", "caption": "c",
     "frames": [{"date": "2026-03-30", "sensor": "Sentinel-1", "url": "frames/radar/a.jpg"},
                {"date": "2026-04-11", "sensor": "Sentinel-1", "url": "frames/radar/b.jpg"}]},
    {"id": "photo", "title": "Photo", "caption": "c",
     "frames": [{"date": "2026-07-14", "sensor": "HLS", "url": "frames/photo/a.jpg"}]}]}


@pytest.fixture
def data(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    root = tmp_path / "data" / "fixture"
    for rel in ("frames/radar/a.jpg", "frames/radar/b.jpg", "frames/photo/a.jpg"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x")
    return tmp_path / "data"


def _write(data, doc):
    (data / "fixture" / "frames.json").write_text(json.dumps(doc), encoding="utf-8")


def test_good_frames_pass(data):
    _write(data, GOOD)
    assert validate(data) == []


def test_a_frame_may_carry_its_own_caption(data):
    doc = _mutate(lambda d: d["sets"][0]["frames"][1].update(sensor="NISAR", caption="NISAR radar picture."))
    _write(data, doc)
    assert validate(data) == []


def test_frames_are_optional(data):
    (data / "fixture" / "frames.json").unlink(missing_ok=True)
    assert validate(data) == []


def _mutate(fn):
    doc = _copy.deepcopy(GOOD)
    fn(doc)
    return doc


@pytest.mark.parametrize("fn", [
    lambda d: d.update(coordinates=CORNERS[:3]),
    lambda d: d["sets"][1].update(id="radar"),
    lambda d: d["sets"][0]["frames"].reverse(),
    lambda d: d["sets"][0]["frames"][1].update(date=d["sets"][0]["frames"][0]["date"]),
    lambda d: d["sets"][0]["frames"][0].update(url="frames/radar/missing.jpg"),
    lambda d: d["sets"][0]["frames"][0].update(url="../fixture/changes.geojson"),
    lambda d: d["sets"][0]["frames"][0].update(url="/etc/passwd"),
    lambda d: d["sets"][0]["frames"][0].update(date="2026-13-01"),
    lambda d: d["sets"][0].update(frames=[]),
    lambda d: d.update(sets=[]),
    lambda d: d["sets"][0]["frames"][0].update(caption=""),
    lambda d: d["sets"][0]["frames"][0].update(caption=5),
])
def test_bad_frames_rejected(data, fn):
    _write(data, _mutate(fn))
    assert validate(data) != []


def test_hidden_must_be_boolean(data):
    path = data / "sites.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["sites"][0]["hidden"] = "yes"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert validate(data) != []


def test_agroparc_and_catalonia_are_hidden():
    sites = {s["id"]: s for s in json.loads((DATA / "sites.json").read_text(encoding="utf-8"))["sites"]}
    assert sites["agroparc"]["hidden"] is True and sites["catalonia"]["hidden"] is True
    assert sites["agroparc"]["ready"]
    assert not sites["muhos"].get("hidden") and not sites["fixture"].get("hidden")


def test_barcelona_is_visible_and_listed_second():
    sites = json.loads((DATA / "sites.json").read_text(encoding="utf-8"))["sites"]
    shown = [s["id"] for s in sites if s["ready"] and not s.get("hidden")]
    assert shown == ["muhos", "barcelona", "fixture"]
