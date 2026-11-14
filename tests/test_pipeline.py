"""Site runner (sarwatch.pipeline) end to end on fake readers: no network, no token, no data cost.

The NISAR and Sentinel-1 readers' network functions are replaced by fakes that serve a speckled stack
with one injected clearing; change detection, export and the contract check are the real ones. Until
sarwatch.s1 is merged, an empty stand-in module carries the Sentinel-1 fakes.
"""
import importlib
import json
import sys
import types
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import sarwatch
from sarwatch import nisar, pipeline
from sarwatch.contract import _check_story, validate

SECRET = "tok-DO-NOT-PRINT-8f3a91c2"
REPO = Path(__file__).resolve().parents[1]
UTC = timezone.utc

# NISAR: the measured Muhos lattice (EPSG:3413, 20 m); 8 passes, HV drops 6 dB from pass 4 on.
N_DAYS = [date(2026, 6, 25) + timedelta(days=12 * i) for i in range(8)]
N_SHAPE, N_RECT, N_CHANGE = (60, 80), (slice(15, 40), slice(20, 55)), 4
N_TRANSFORM, N_EPSG = (20.0, 0.0, 2617240.0, 0.0, -20.0, -898540.0), 3413
# Sentinel-1: UTM 35N, 30 m, over the same ground; 10 passes, VH drops 6 dB from pass 5 on.
S_DAYS = [date(2026, 1, 5) + timedelta(days=24 * i) for i in range(10)]
S_SHAPE, S_RECT, S_CHANGE = (40, 50), (slice(10, 30), slice(10, 40)), 5
S_TRANSFORM, S_EPSG = (30.0, 0.0, 454020.0, 0.0, -30.0, 7192110.0), 32635


def image(seed, shape, pols, change_pol, changed, rect):
    """Two-channel speckle (16 looks, gamma) at -10 / -17 dB; change_pol 6 dB darker inside rect if changed."""
    rng = np.random.default_rng(seed)
    data = {p: rng.gamma(16, m / 16, size=shape).astype(np.float32) for p, m in zip(pols, (0.1, 0.02))}
    if changed:
        data[change_pol][rect] *= np.float32(10 ** (-6 / 10))
    return data


def at(day):
    return datetime(day.year, day.month, day.day, 2, 3, 20, tzinfo=UTC)


class FakeNisar:
    """Search + read_crop for the archive; counts reads and checks the token it is given."""

    def __init__(self):
        self.searches, self.reads, self.transforms = 0, [], {}

    def search(self, bbox, start=None, end=None):
        self.searches += 1
        stack = [nisar.Granule(f"GCOV_157_A_035_{d:%Y%m%d}", f"https://archive.test/157/{d}.h5", at(d), 157, 35,
                               "ASCENDING", "PROVISIONAL", 2050.0) for d in N_DAYS]
        # another track with more dates: pick_track alone would choose it; the site's fixed track must not
        decoy = [nisar.Granule(f"GCOV_85_D_036_{i}", f"https://archive.test/85/{i}.h5",
                               at(date(2026, 6, 20) + timedelta(days=6 * i)), 85, 36, "DESCENDING", "PROVISIONAL", 2050.0)
                 for i in range(12)]
        return stack + decoy

    def read_crop(self, url, bbox, pols=("HH", "HV"), token=None, frequency="A"):
        assert token == SECRET
        assert "/157/" in url, "read a granule outside the site's fixed track"
        day = date.fromisoformat(url.rsplit("/", 1)[1][:10])
        self.reads.append(day)
        i = N_DAYS.index(day)
        return nisar.Crop(image(i, N_SHAPE, pols, "HV", i >= N_CHANGE, N_RECT),
                          self.transforms.get(day, N_TRANSFORM), N_EPSG, at(day), 25_000_000, 0.01)


@dataclass
class Scene:
    name: str
    start: datetime


class FakeS1:
    def __init__(self):
        self.reads, self.thin_args, self.stats = [], None, {}  # stats: the reader's last_read_stats

    def search(self, bbox, start=None, end=None):
        return [Scene(f"OPERA_RTC_S1_{d:%Y%m%d}", at(d)) for d in S_DAYS]

    def pick_burst(self, scenes, bbox):
        return scenes

    def thin(self, scenes, max_dates=None, min_gap_days=None):
        self.thin_args = (max_dates, min_gap_days)
        return scenes[:max_dates] if max_dates else scenes

    def read_stack(self, scenes, bbox, pols=("VV", "VH"), token=None):
        assert token == SECRET and len(scenes) == 1
        day = scenes[0].start.date()
        self.reads.append(day)
        i = S_DAYS.index(day)
        data = image(100 + i, S_SHAPE, pols, "VH", i >= S_CHANGE, S_RECT)
        self.stats.update(bytes=3_000_000, dates=1)
        return {p: a[None] for p, a in data.items()}, [day], S_TRANSFORM, S_EPSG


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Fake archive readers, token in the environment, no real .env, app data and cache under tmp_path."""
    n, s = FakeNisar(), FakeS1()
    monkeypatch.setattr(nisar, "search", n.search)
    monkeypatch.setattr(nisar, "read_crop", n.read_crop)
    try:
        s1mod = importlib.import_module("sarwatch.s1")
    except ImportError:  # until the Sentinel-1 reader is merged: an empty module the fakes fill in
        s1mod = types.ModuleType("sarwatch.s1")
        monkeypatch.setitem(sys.modules, "sarwatch.s1", s1mod)
        monkeypatch.setattr(sarwatch, "s1", s1mod, raising=False)
    for name in ("search", "pick_burst", "thin", "read_stack"):
        monkeypatch.setattr(s1mod, name, getattr(s, name), raising=False)
    monkeypatch.setattr(s1mod, "last_read_stats", s.stats, raising=False)

    monkeypatch.setenv("EARTHDATA_TOKEN", SECRET)
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)  # .env lookups land in tmp_path, never the real repo
    data = tmp_path / "app" / "data"
    data.mkdir(parents=True)
    # the real index, every site not ready, so the validator needs no other site folders
    text = (REPO / "app" / "data" / "sites.json").read_bytes().decode("utf-8")
    (data / "sites.json").write_bytes(text.replace('"ready": true', '"ready": false').encode("utf-8"))
    cache = tmp_path / "stacks"
    args = ["--out", str(data), "--cache", str(cache)]
    return SimpleNamespace(nisar=n, s1=s, data=data, cache=cache, args=args)


def site_entry(data, site_id):
    index = json.loads((data / "sites.json").read_text(encoding="utf-8"))
    return next(s for s in index["sites"] if s["id"] == site_id)


def features(data, site_id):
    return json.loads((data / site_id / "changes.geojson").read_text(encoding="utf-8"))["features"]


# ---------------------------------------------------------------- end to end


def test_run_builds_a_valid_site_and_a_rerun_fetches_nothing(fake, capsys):
    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 0

    assert sorted(fake.nisar.reads) == N_DAYS
    assert fake.nisar.reads[:2] == [N_DAYS[0], N_DAYS[-1]]  # ends first
    assert pipeline.cached_days(fake.cache / "muhos" / "nisar") == N_DAYS
    feats = features(fake.data, "muhos")
    clearing = [f["properties"] for f in feats if f["properties"]["type"] == "clearing"]
    assert len(clearing) == 1 and clearing[0]["sensor"] == "NISAR L-band"
    assert abs(N_DAYS.index(date.fromisoformat(clearing[0]["first_date"])) - N_CHANGE) <= 1
    assert 25 <= clearing[0]["area_ha"] <= 45  # 875 px of 0.04 ha = 35 ha on the grid
    entry = site_entry(fake.data, "muhos")
    assert entry["ready"] is True and entry["time_range"] == [str(N_DAYS[0]), str(N_DAYS[-1])]
    story = json.loads((fake.data / "muhos" / "story.json").read_text(encoding="utf-8"))
    assert story["headline"] == "Muhos, Finland"
    assert validate(fake.data) == []
    out = capsys.readouterr().out
    assert "contract: OK" in out and "clearing 1" in out and "fetched this run: 8 dates, 200.0 MB" in out

    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 0  # everything cached: searches, fetches nothing
    assert len(fake.nisar.reads) == len(N_DAYS)
    assert "fetched this run: 0 dates" in capsys.readouterr().out

    searches = fake.nisar.searches  # offline rerun with another threshold: no network at all
    assert pipeline.main(["muhos", "--no-s1", "--offline", "--threshold-db", "4", *fake.args]) == 0
    assert fake.nisar.searches == searches and len(fake.nisar.reads) == len(N_DAYS)


def test_s1_history_runs_alongside_nisar(fake, monkeypatch, capsys):
    site = pipeline.SITES["muhos"]  # the machinery, not the Muhos tuning (its skip dates and baseline length)
    monkeypatch.setattr(site, "skip_dates", ())
    monkeypatch.setattr(site, "s1", pipeline.S1Settings(start=date(2026, 1, 1), max_dates=30))
    assert pipeline.main(["muhos", *fake.args]) == 0
    assert "fetched this run: 18 dates, 230.0 MB" in capsys.readouterr().out  # 8 x 25 MB + 10 x 3 MB

    assert fake.s1.thin_args == (30, None)  # the site's Sentinel-1 settings reach thin()
    assert sorted(fake.s1.reads) == S_DAYS
    assert pipeline.cached_days(fake.cache / "muhos" / "s1") == S_DAYS
    sensors = {f["properties"]["sensor"] for f in features(fake.data, "muhos")
               if f["properties"]["type"] == "clearing"}
    assert sensors == {"NISAR L-band", "Sentinel-1 C-band"}
    assert site_entry(fake.data, "muhos")["time_range"] == [str(S_DAYS[0]), str(N_DAYS[-1])]
    assert validate(fake.data) == []


def test_offline_with_an_empty_cache_fails_clearly(fake, capsys):
    before = (fake.data / "sites.json").read_bytes()

    assert pipeline.main(["muhos", "--offline", *fake.args]) == 2

    err = capsys.readouterr().err
    assert "--offline" in err and "nothing cached" in err and "without --offline" in err
    assert fake.nisar.searches == 0 and fake.nisar.reads == [] and fake.s1.reads == []
    assert (fake.data / "sites.json").read_bytes() == before
    assert not (fake.data / "muhos").exists()


def test_max_dates_fetches_ends_first_and_resumes(fake):
    assert pipeline.main(["muhos", "--no-s1", "--fetch-only", "--max-dates", "2", *fake.args]) == 0
    assert fake.nisar.reads == [N_DAYS[0], N_DAYS[-1]]
    assert not (fake.data / "muhos").exists()  # --fetch-only stops before detection
    assert site_entry(fake.data, "muhos")["ready"] is False

    assert pipeline.main(["muhos", "--no-s1", "--fetch-only", "--max-dates", "3", *fake.args]) == 0
    assert fake.nisar.reads[2:] == [N_DAYS[1], N_DAYS[-2], N_DAYS[2]]

    assert pipeline.main(["muhos", "--max-dates", "4", *fake.args]) == 0  # the budget spans both sensors
    assert len(fake.nisar.reads) == len(N_DAYS) and len(fake.s1.reads) == 1
    assert site_entry(fake.data, "muhos")["ready"] is True  # NISAR is complete, Sentinel-1 skipped (1 date)
    assert validate(fake.data) == []


def test_fetching_without_a_token_fails_before_any_read(fake, monkeypatch, capsys):
    monkeypatch.delenv("EARTHDATA_TOKEN")

    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 2

    assert "EARTHDATA_TOKEN" in capsys.readouterr().err and fake.nisar.reads == []


# ---------------------------------------------------------------- token


@pytest.mark.parametrize("key", ["EARTHDATA_TOKEN", "EARTH_DATA_TOKEN"])
def test_token_from_dotenv_both_spellings(tmp_path, monkeypatch, key):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    assert pipeline.load_token(tmp_path) is None
    (tmp_path / ".env").write_text(f"# local secrets\nOTHER=1\n\n{key} = \"{SECRET}\"\n", encoding="utf-8")

    assert pipeline.load_token(tmp_path) == SECRET
    monkeypatch.setenv("EARTHDATA_TOKEN", "from-env")
    assert pipeline.load_token(tmp_path) == "from-env"  # the environment wins


def test_token_from_dotenv_is_used_and_never_printed(fake, monkeypatch, capsys, caplog):
    monkeypatch.delenv("EARTHDATA_TOKEN")
    (fake.cache.parent / ".env").write_text(f"EARTH_DATA_TOKEN={SECRET}\n", encoding="utf-8")  # = REPO_ROOT here
    caplog.set_level("DEBUG")

    assert pipeline.main(["muhos", *fake.args]) == 0

    assert fake.nisar.reads and fake.s1.reads  # the fakes assert they got the token
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err + caplog.text


# ---------------------------------------------------------------- site index and story


def test_sites_json_update_keeps_other_sites_untouched(tmp_path):
    path = tmp_path / "sites.json"
    original = (REPO / "app" / "data" / "sites.json").read_bytes()
    path.write_bytes(original)
    before = json.loads(original)

    pipeline.update_sites_index(path, "agroparc", (date(2024, 1, 5), date(2026, 11, 2)))

    after = json.loads(path.read_bytes())
    assert [s for s in after["sites"] if s["id"] != "agroparc"] == [s for s in before["sites"] if s["id"] != "agroparc"]
    entry = next(s for s in after["sites"] if s["id"] == "agroparc")
    old = next(s for s in before["sites"] if s["id"] == "agroparc")
    assert entry == {**old, "ready": True, "time_range": ["2024-01-05", "2026-11-02"]}
    old_lines, new_lines = original.decode().splitlines(True), path.read_bytes().decode().splitlines(True)
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    assert len(old_lines) == len(new_lines) and changed  # same layout and line endings, edited in place
    start = next(i for i, line in enumerate(old_lines) if '"id": "agroparc"' in line)
    assert all(start <= i < start + 3 for i in changed)


def test_sites_json_falls_back_to_the_house_style_when_it_cannot_edit_in_place(tmp_path):
    index = json.loads((REPO / "app" / "data" / "sites.json").read_bytes())
    del index["sites"][0]["ready"]  # nothing to edit in place
    path = tmp_path / "sites.json"
    path.write_text(json.dumps(index), encoding="utf-8")

    pipeline.update_sites_index(path, index["sites"][0]["id"], ("2026-06-25", "2026-11-04"))

    after = json.loads(path.read_text(encoding="utf-8"))
    index["sites"][0].update(ready=True, time_range=["2026-06-25", "2026-11-04"])
    assert after == index
    assert path.read_text(encoding="utf-8").count('{"id": ') == len(index["sites"])  # one block per site


def test_unknown_site_in_index_fails_before_fetching(fake, capsys):
    index = json.loads((fake.data / "sites.json").read_text(encoding="utf-8"))
    index["sites"] = [s for s in index["sites"] if s["id"] != "muhos"]
    (fake.data / "sites.json").write_text(json.dumps(index), encoding="utf-8")

    assert pipeline.main(["muhos", *fake.args]) == 2
    assert "not in" in capsys.readouterr().err and fake.nisar.searches == 0


def test_placeholder_story_is_written_once_and_never_overwritten(tmp_path):
    site = tmp_path / "muhos"
    assert pipeline.ensure_story(site, "Muhos, Finland") is True
    errors = []
    _check_story(site, errors)
    assert errors == []

    mine = '{"headline": "Written by the verdict track", "story": ["Real text."]}'
    (site / "story.json").write_text(mine, encoding="utf-8")
    assert pipeline.ensure_story(site, "Muhos, Finland") is False
    assert (site / "story.json").read_text(encoding="utf-8") == mine


def test_a_run_keeps_an_existing_story(fake):
    site = fake.data / "muhos"
    site.mkdir()
    mine = json.dumps({"headline": "Clear-cut at Muhos", "story": ["Sourced text."], "events": [], "sources": []})
    (site / "story.json").write_text(mine, encoding="utf-8")

    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 0
    assert (site / "story.json").read_text(encoding="utf-8") == mine


# ---------------------------------------------------------------- cache and grids


def frame(day, transform=N_TRANSFORM, bbox=(25.94, 64.80, 26.15, 64.89)):
    return pipeline.Frame(day=day, data=image(0, N_SHAPE, ("HH", "HV"), "HV", False, N_RECT), transform=transform,
                          epsg=N_EPSG, bbox=bbox, source=f"granule {day}", mb=12.5, seconds=1.0)


def test_cache_round_trip(tmp_path):
    f = frame(N_DAYS[0])
    pipeline.save_frame(pipeline.cache_path(tmp_path, f.day), f)

    g = pipeline.load_frame(pipeline.cache_path(tmp_path, f.day))

    assert (g.day, g.transform, g.epsg, g.bbox, g.source, g.mb) == (f.day, f.transform, f.epsg, f.bbox, f.source, f.mb)
    assert all(np.array_equal(g.data[p], f.data[p]) for p in f.data)
    assert not list(tmp_path.glob("*.part"))


def test_grid_mismatch_between_dates_raises(tmp_path):
    shifted = (20.0, 0.0, N_TRANSFORM[2] + 20.0, 0.0, -20.0, N_TRANSFORM[5])  # one pixel east
    pipeline.save_frame(pipeline.cache_path(tmp_path, N_DAYS[0]), frame(N_DAYS[0]))
    pipeline.save_frame(pipeline.cache_path(tmp_path, N_DAYS[1]), frame(N_DAYS[1], shifted))

    with pytest.raises(ValueError, match=str(N_DAYS[1])):
        pipeline.load_stack(tmp_path)
    stack, dates, transform, epsg = pipeline.load_stack(tmp_path, [N_DAYS[0]])
    assert stack["HV"].shape == (1, *N_SHAPE) and dates == [N_DAYS[0]] and epsg == N_EPSG


def test_cached_window_for_another_bbox_is_refused(tmp_path):
    pipeline.save_frame(pipeline.cache_path(tmp_path, N_DAYS[0]), frame(N_DAYS[0], bbox=(26.0, 64.8, 26.1, 64.9)))

    with pytest.raises(pipeline.PipelineError, match="bbox"):
        pipeline.load_stack(tmp_path, bbox=(25.94, 64.80, 26.15, 64.89))


def test_a_fetched_date_on_another_grid_stops_the_run_unsaved(fake, capsys):
    fake.nisar.transforms[N_DAYS[-1]] = (20.0, 0.0, N_TRANSFORM[2] + 40.0, 0.0, -20.0, N_TRANSFORM[5])

    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 2

    assert "another grid" in capsys.readouterr().err
    assert pipeline.cached_days(fake.cache / "muhos" / "nisar") == [N_DAYS[0]]


def test_sensor_defaults_and_overrides():
    site = pipeline.SITES["agroparc"]
    assert pipeline._params(site, "nisar").boxcar == 5 and pipeline._params(site, "s1").boxcar == 3
    p = pipeline._params(site, "s1", threshold_db=4.0, min_area_ha=1.0)
    assert (p.boxcar, p.threshold_db, p.min_area_ha) == (3, 4.0, 1.0)
    assert site.s1.params.threshold_db == 3.0  # the site definition is not modified


def test_site_overrides_then_command_line_overrides(monkeypatch):
    site = pipeline.SITES["agroparc"]
    monkeypatch.setattr(site, "params", {"boxcar": 7, "threshold_db": 2.5})
    p = pipeline._params(site, "nisar")
    assert (p.boxcar, p.threshold_db, p.min_area_ha) == (7, 2.5, 0.5)
    assert pipeline._params(site, "nisar", threshold_db=4.0).threshold_db == 4.0  # the command line wins
    assert site.nisar.params.boxcar == 5  # the sensor defaults are not modified
    monkeypatch.setattr(site, "params", {"treshold_db": 2.5})
    with pytest.raises(pipeline.PipelineError, match="treshold_db"):
        pipeline._params(site, "nisar")


def test_skip_dates_from_the_site_or_the_command_line(fake, monkeypatch, capsys, caplog):
    caplog.set_level("INFO", logger="sarwatch.pipeline")
    monkeypatch.setattr(pipeline.SITES["muhos"], "skip_dates", (str(N_DAYS[-1]),))
    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 0
    assert sorted(fake.nisar.reads) == N_DAYS  # a skipped date is still fetched and cached, only not used
    assert site_entry(fake.data, "muhos")["time_range"] == [str(N_DAYS[0]), str(N_DAYS[-2])]
    assert f"{len(N_DAYS) - 1} dates" in capsys.readouterr().out

    skip = f"{N_DAYS[0]},{N_DAYS[-1]}"  # the flag replaces the site's list
    assert pipeline.main(["muhos", "--no-s1", "--offline", "--skip-dates", skip, *fake.args]) == 0
    assert site_entry(fake.data, "muhos")["time_range"] == [str(N_DAYS[1]), str(N_DAYS[-2])]
    assert pipeline.main(["muhos", "--no-s1", "--offline", "--skip-dates", "", *fake.args]) == 0  # '' = all dates
    assert site_entry(fake.data, "muhos")["time_range"] == [str(N_DAYS[0]), str(N_DAYS[-1])]
    span = f"{N_DAYS[1]}..{N_DAYS[3]}"  # an inclusive range
    assert pipeline.main(["muhos", "--no-s1", "--offline", "--skip-dates", span, *fake.args]) == 0
    assert f"left out 3 date(s), {N_DAYS[1]}, {N_DAYS[2]}, {N_DAYS[3]}" in caplog.text
    assert pipeline.main(["muhos", "--no-s1", "--offline", "--skip-dates", "4 Nov", *fake.args]) == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_water_is_left_out_of_detection(fake, monkeypatch):
    site = pipeline.SITES["muhos"]
    monkeypatch.setattr(site, "skip_dates", ())
    monkeypatch.setattr(site, "params", {})
    monkeypatch.setattr(site, "nisar", pipeline.NisarSettings(start=date(2026, 6, 1), track=157, frame=35))
    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 0
    assert any(f["properties"]["type"] == "clearing" for f in features(fake.data, "muhos"))
    # the changed rectangle is dark in HH (-10 dB) but brighter than -12 dB: land, still found
    site.nisar.water_db = -12.0
    assert pipeline.main(["muhos", "--no-s1", "--offline", *fake.args]) == 0
    assert any(f["properties"]["type"] == "clearing" for f in features(fake.data, "muhos"))
    site.nisar.water_db = -5.0  # everything is "water": nothing left to detect
    assert pipeline.main(["muhos", "--no-s1", "--offline", *fake.args]) == 0
    assert features(fake.data, "muhos") == []


def test_water_mask_comes_from_the_baseline_passes():
    hh = np.full((6, 20, 20), 0.1, dtype=np.float32)  # land at -10 dB
    hh[:3, 2:6, 2:6] = 1e-3   # water (-30 dB) in the 3 baseline passes, land later (a drained pond)
    hh[3:, 12:16, 12:16] = 1e-3  # land in the baseline, water later (a flooded field): a change, not masked
    hh[4, 0, 19] = np.nan
    valid = pipeline._water_mask({"HH": hh, "HV": hh}, "nisar", n_early=3, water_db=-16.0)
    assert valid.shape == (20, 20)
    assert not valid[2:6, 2:6].any() and not valid[1, 3] and valid[0, 3]  # the water, plus one pixel around it
    assert valid[12:16, 12:16].all() and valid[0, 19]
    # with only two dates, the baseline is the first one, as in detect_changes
    assert pipeline._water_mask({"HH": hh[2:4]}, "nisar", n_early=3, water_db=-16.0)[3, 3] == False  # noqa: E712


def test_bad_skip_dates_fail_before_any_fetch(fake, monkeypatch, capsys):
    monkeypatch.setattr(pipeline.SITES["muhos"], "skip_dates", ("2026-08-01..2026-07-01",))
    assert pipeline.main(["muhos", "--no-s1", *fake.args]) == 2
    assert "ends before it starts" in capsys.readouterr().err and fake.nisar.reads == []
    monkeypatch.setattr(pipeline.SITES["muhos"], "params", {"treshold_db": 2.0})
    assert pipeline.main(["muhos", "--no-s1", "--skip-dates", "", *fake.args]) == 2
    assert "treshold_db" in capsys.readouterr().err and fake.nisar.reads == []
