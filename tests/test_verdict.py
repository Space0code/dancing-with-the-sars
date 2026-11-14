"""One test per verdict rule (kb/verdict-rules.md), plus wording, re-run safety and the command line."""
import json
import shutil
from pathlib import Path

import pytest

from sarwatch.contract import validate
from sarwatch.verdict import apply_file, judge, load_records_file, records_for

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
FIXTURE_RECORDS = ROOT / "tests" / "fixtures" / "verdict" / "fixture_records.json"


def ok(**kw):
    return {"checked": True, "source": "Test source", "url": None, **kw}


def records(zone=None, built=0, inside=False, plants=(), fire=None, **over):
    out = {
        "protected": ok(inside=inside, areas=[{"name": "Serra de Test", "kind": "PEIN"}] if inside else []),
        "cadastre": ok(buildings=built, built_since=built),
        "zoning": ok(zone=zone),
        "solar": ok(plants=list(plants)),
    }
    if fire:
        out["fire"] = ok(recorded=True)
    out.update(over)
    return out


def change(area=10.0, ctype="clearing", explain="Radar saw the tree signal drop by -6 dB here."):
    return {"id": "t-0001", "type": ctype, "area_ha": area, "first_date": "2026-03-01", "explain": explain}


def codes(reasons):
    return [r["code"] for r in reasons]


def test_protected_area_is_high_concern():
    verdict, reasons, _ = judge(change(area=0.5), records(inside=True))
    assert verdict == "high_concern" and codes(reasons)[0] == "protected_area"
    assert "Serra de Test" in reasons[0]["text"]


def test_big_clearing_on_non_buildable_land_without_record_is_high_concern():
    verdict, reasons, _ = judge(change(area=5.0), records(zone="non_buildable"))
    assert verdict == "high_concern"
    assert {"zoning_non_buildable", "no_record_found"} <= set(codes(reasons))


def test_big_earthworks_on_non_buildable_land_without_record_is_high_concern():
    assert judge(change(area=8, ctype="earthworks"), records(zone="non_buildable"))[0] == "high_concern"


def test_non_buildable_with_matching_record_is_only_review():
    verdict, reasons, _ = judge(change(area=20), records(zone="non_buildable", built=1))
    assert verdict == "review" and "cadastre_building_found" in codes(reasons)


def test_non_buildable_structure_is_review_not_high_concern():
    assert judge(change(area=30, ctype="structure"), records(zone="non_buildable"))[0] == "review"


def test_small_change_on_non_buildable_land_is_review():
    verdict, reasons, _ = judge(change(area=1.2), records(zone="non_buildable"))
    assert verdict == "review" and "small_area" in codes(reasons)


def test_two_ha_without_record_is_review():
    verdict, reasons, _ = judge(change(area=2.0), records(zone="urban"))
    assert verdict == "review" and "no_record_found" in codes(reasons) and "zoning_urban" in codes(reasons)


def test_unknown_zoning_large_without_record_is_review():
    assert judge(change(area=40), records(zone=None))[0] == "review"


def test_urban_with_building_record_is_expected():
    verdict, reasons, _ = judge(change(area=6, ctype="structure"), records(zone="urban", built=3))
    assert verdict == "expected" and "cadastre_building_found" in codes(reasons)


def test_planned_sector_is_expected():
    verdict, reasons, _ = judge(change(area=30), records(zone="developable"))
    assert verdict == "expected" and "planned_sector" in codes(reasons)


def test_listed_solar_plant_is_a_matching_record():
    verdict, reasons, _ = judge(change(area=12), records(zone="urban", plants=[{"name": "Solar X"}]))
    assert verdict == "expected" and "solar_plant_listed" in codes(reasons)


def test_solar_listing_does_not_explain_ground_motion():
    assert judge(change(area=12, ctype="ground_motion"), records(plants=[{"name": "Solar X"}]))[0] == "review"


def test_small_change_without_flags_is_expected():
    verdict, reasons, _ = judge(change(area=0.8), records(zone="urban"))
    assert verdict == "expected" and "small_area" in codes(reasons)


def test_recorded_fire_is_expected_even_in_a_protected_area():
    verdict, reasons, _ = judge(change(area=60, ctype="fire"), records(inside=True, fire=True))
    assert verdict == "expected"
    assert codes(reasons)[0] == "fire_recorded"
    assert [r["effect"] for r in reasons if r["code"] == "protected_area"] == ["neutral"]


def test_fire_type_without_a_record_follows_the_normal_rules():
    assert judge(change(area=60, ctype="fire"), records(zone=None))[0] == "review"


def test_unchecked_records_fall_back_to_size_and_say_so():
    unchecked = {
        k: {"checked": False, "source": k, "url": None, "error": "timeout"}
        for k in ("protected", "cadastre", "zoning", "solar")
    }
    big = judge(change(area=9), unchecked)
    small = judge(change(area=0.9), unchecked)
    assert big[0] == "review" and small[0] == "expected"
    assert codes(big[1]).count("records_unavailable") == 4 and "no_record_found" not in codes(big[1])


def test_missing_records_behave_like_unchecked():
    assert judge(change(area=9), {})[0] == "review"


def test_protected_area_still_flagged_when_only_zoning_is_unchecked():
    recs = records(inside=True, zoning={"checked": False, "source": "MUC", "url": None})
    verdict, reasons, _ = judge(change(), recs)
    assert verdict == "high_concern" and "records_unavailable" in codes(reasons)


def test_reasons_follow_the_contract_shape_and_never_accuse():
    cases = [records(inside=True), records(zone="non_buildable"), records(zone="urban"), records(fire=True), {}]
    for recs in cases:
        verdict, reasons, explain = judge(change(), recs)
        assert verdict in {"expected", "review", "high_concern"} and reasons and explain
        for r in reasons:
            assert set(r) == {"code", "text", "source", "url", "effect"}
            assert r["effect"] in {"raises", "lowers", "neutral"} and r["source"] and r["text"]
        blob = json.dumps([reasons, explain]).lower()
        assert "illegal" not in blob and "unlawful" not in blob and "violat" not in blob


def test_explain_keeps_the_radar_sentence_and_adds_the_records():
    _, _, explain = judge(change(), records(zone="non_buildable"))
    assert explain.startswith("Radar saw the tree signal drop by -6 dB here.")
    assert "non-buildable" in explain


def test_judge_is_pure():
    c, r = change(), records(zone="urban")
    before = json.dumps([c, r], sort_keys=True)
    judge(c, r)
    assert json.dumps([c, r], sort_keys=True) == before


# ---- hand-entered records + command line ----


def test_records_file_defaults_and_per_change_override():
    doc = load_records_file(FIXTURE_RECORDS)
    recs = records_for(doc, "fixture-0003")
    assert recs["protected"]["inside"] is True and recs["zoning"]["checked"] is True
    assert records_for(doc, "unknown-id")["protected"]["inside"] is False


@pytest.fixture
def fixture_copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


def test_cli_labels_the_fixture_and_result_passes_the_contract(fixture_copy, capsys):
    from sarwatch.verdict import main

    path = fixture_copy / "fixture" / "changes.geojson"
    assert main([str(path), "--records", str(FIXTURE_RECORDS)]) == 0
    assert validate(fixture_copy) == []
    out = capsys.readouterr().out
    assert "labels before:" in out and "labels after:" in out
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    verdicts = {f["properties"]["id"]: f["properties"]["verdict"] for f in features}
    assert verdicts == {
        "fixture-0001": "high_concern", "fixture-0002": "expected", "fixture-0003": "high_concern",
        "fixture-0004": "review", "fixture-0005": "expected", "fixture-0006": "high_concern",
        "fixture-0007": "expected",
    }


def test_rerun_recomputes_from_scratch(fixture_copy):
    path = fixture_copy / "fixture" / "changes.geojson"
    apply_file(path, FIXTURE_RECORDS)
    first = path.read_text(encoding="utf-8")
    apply_file(path, FIXTURE_RECORDS)
    assert path.read_text(encoding="utf-8") == first


def test_dry_run_writes_nothing(fixture_copy):
    path = fixture_copy / "fixture" / "changes.geojson"
    original = path.read_text(encoding="utf-8")
    apply_file(path, FIXTURE_RECORDS, dry_run=True)
    assert path.read_text(encoding="utf-8") == original


def test_site_outside_spain_uses_no_catalan_lookups(fixture_copy):
    sites = json.loads((fixture_copy / "sites.json").read_text(encoding="utf-8"))
    next(s for s in sites["sites"] if s["id"] == "fixture")["country"] = "FI"
    (fixture_copy / "sites.json").write_text(json.dumps(sites), encoding="utf-8")

    def boom(*args, **kwargs):
        raise AssertionError("lookups must not run for a site outside Catalonia")

    path = fixture_copy / "fixture" / "changes.geojson"
    _, after = apply_file(path, lookup=boom)
    assert sum(after.values()) == 7
    assert validate(fixture_copy) == []
