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


def plant(ha=12.0, status="Autoritzat"):
    return {"name": "Solar X", "status": status, "ha": ha, "ha_in_municipality": ha}


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
    verdict, reasons, _ = judge(change(area=12), records(zone="urban", plants=[plant()]))
    assert verdict == "expected" and codes(reasons)[0] == "solar_plant_listed"


def test_solar_listing_does_not_explain_ground_motion():
    assert judge(change(area=12, ctype="ground_motion"), records(plants=[plant()]))[0] == "review"


def test_small_change_without_flags_is_expected():
    verdict, reasons, _ = judge(change(area=0.8), records(zone="urban"))
    assert verdict == "expected" and "small_area" in codes(reasons)


def test_recorded_fire_is_expected_even_in_a_protected_area():
    verdict, reasons, _ = judge(change(area=60, ctype="fire"), records(inside=True, fire=True))
    assert verdict == "expected"
    assert codes(reasons)[0] == "fire_recorded"
    assert [r["effect"] for r in reasons if r["code"] == "protected_area"] == ["neutral"]


def test_a_recorded_fire_from_the_lookup_makes_a_burn_scar_expected():
    """The shape ``context.fire.lookup`` returns: ``recorded`` plus the list of fires."""
    fire_record = ok(recorded=True, fires=[{"name": "Colera", "date": "2023-08-04", "area_ha": 541, "overlap_share": 1.0}])
    verdict, reasons, _ = judge(change(area=40), {**records(zone="non_buildable"), "fire": fire_record})
    assert verdict == "expected" and codes(reasons)[0] == "fire_recorded"


def test_fire_reason_names_the_fire_and_says_most_likely():
    fire_record = ok(source="EFFIS burnt areas (European Commission JRC)", recorded=True, url="https://example.org/effis",
                     fires=[{"name": "Colera", "date": "2023-08-04", "area_ha": 541.0, "overlap_share": 1.0}])
    _, reasons, explain = judge(change(area=40), {**records(zone="non_buildable"), "fire": fire_record})
    text = reasons[0]["text"]
    assert "Colera" in text and "2023-08-04" in text and "541 ha" in text and "EFFIS burnt areas" in text
    assert "most likely a burn scar" in text and "natural change" not in text
    assert reasons[0]["url"] == "https://example.org/effis"  # keeps the record's link


def test_fire_reason_without_a_fire_list_still_reads_well():
    for fires in ([], None):
        rec = ok(recorded=True) if fires is None else ok(recorded=True, fires=fires)
        _, reasons, _ = judge(change(area=40), {**records(zone="non_buildable"), "fire": rec})
        assert reasons[0]["text"].startswith("A recorded wildfire burned here, so this is most likely a burn scar")


def test_a_failed_fire_lookup_is_reported_not_silent():
    failed = {"checked": False, "source": "EFFIS", "url": None, "error": "timeout"}
    verdict, reasons, _ = judge(change(area=40), {**records(zone="urban"), "fire": failed})
    assert verdict == "review" and "records_unavailable" in codes(reasons)
    assert any("wildfire map" in r["text"] for r in reasons)
    assert "records_unavailable" not in codes(judge(change(area=40), records(zone="urban"))[1])  # not asked: silent


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
    _, after, _ = apply_file(path, lookup=boom)
    assert sum(after.values()) == 7
    assert validate(fixture_copy) == []
    reasons = [r for f in json.loads(path.read_text(encoding="utf-8"))["features"] for r in f["properties"]["reasons"]]
    assert reasons and "records_unavailable" not in codes(reasons)  # Catalan services are not applicable in Finland


def test_offline_flag_serves_lookups_from_the_cache_only(fixture_copy, monkeypatch, capsys):
    from sarwatch.context import _common
    from sarwatch.verdict import main

    monkeypatch.setattr(_common, "OFFLINE", False)
    monkeypatch.setattr(_common, "CACHE_DIR", fixture_copy / "empty-cache")  # nothing cached: every lookup misses
    path = fixture_copy / "fixture" / "changes.geojson"
    original = path.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as stop:  # no network is used (it would hang or succeed): all lookups fail
        main([str(path), "--offline"])
    assert "Nothing written" in str(stop.value) and _common.OFFLINE is True
    assert path.read_text(encoding="utf-8") == original


# ---- review fixes on PR #31 ----


def test_small_or_refused_solar_listing_does_not_explain_a_big_change():
    """Real Agroparc: 258 ha of earthworks on non-buildable land, one 3 ha plant 'in processing' in the municipality."""
    recs = records(zone="non_buildable", plants=[plant(ha=3, status="En tramitació")])
    verdict, reasons, _ = judge(change(area=258, ctype="earthworks"), recs)
    assert verdict == "high_concern" and "solar_plant_other" in codes(reasons)
    refused = judge(change(area=12), records(zone="urban", plants=[plant(status="No autoritzat")]))
    assert refused[0] == "review" and "solar_plant_other" in codes(refused[1])
    no_size = judge(change(area=12), records(zone="urban", plants=[{"name": "X", "status": "Autoritzat"}]))
    assert no_size[0] == "review"
    assert judge(change(area=12), records(zone="urban", plants=[plant(ha=6)]))[0] == "expected"  # half as large


def test_recorded_fire_does_not_explain_a_new_structure():
    verdict, reasons, _ = judge(change(area=20, ctype="structure"), records(zone="urban", fire=True))
    assert verdict == "review" and codes(reasons).count("fire_recorded") == 1
    assert next(r for r in reasons if r["code"] == "fire_recorded")["effect"] == "neutral"
    assert judge(change(area=20, ctype="other"), records(fire=True))[0] == "expected"


def test_protected_area_without_a_name_does_not_crash():
    recs = records(inside=True)
    recs["protected"]["areas"] = [{"name": None, "kind": "PEIN"}, {"kind": "Natura 2000 SPA"}]
    verdict, reasons, _ = judge(change(), recs)
    assert verdict == "high_concern" and "PEIN" in reasons[0]["text"]


def test_deciding_reason_comes_first_and_explain_never_contradicts_the_label():
    cases = [
        (change(area=1), records(zone=None)),  # small, no zoning class
        (change(area=6, ctype="structure"), records(zone="urban", built=2)),
        (change(area=9), records(zone="urban")),
        (change(area=60, ctype="fire"), records(fire=True)),
        (change(area=0.5), records(inside=True)),
    ]
    for ch, recs in cases:
        verdict, reasons, explain = judge(ch, recs)
        assert reasons[0]["text"] in explain  # the deciding reason is what the sentence says
        wrong = "raises" if verdict == "expected" else "lowers"
        assert all(r["text"] not in explain for r in reasons if r["effect"] == wrong)
    verdict, reasons, explain = judge(change(area=1), records(zone=None))
    assert verdict == "expected" and codes(reasons)[0] == "small_area" and "No registered building" not in explain


def test_protected_buffer_zone_or_edge_touch_is_review_not_high_concern():
    buffer = records(inside=True, zone="urban", built=1)  # a building record would make this "expected"
    buffer["protected"]["areas"] = [{"name": "Parc X", "kind": "natural park buffer zone"}]
    verdict, reasons, _ = judge(change(area=3), buffer)
    assert verdict == "review" and codes(reasons)[0] == "protected_buffer"
    edge = records(inside=True, zone="urban", built=1)
    edge["protected"]["overlap_share"] = 0.0004
    assert judge(change(area=3), edge)[0] == "review"
    big = records(inside=True, zone="non_buildable")
    big["protected"]["areas"] = [{"name": "Parc X", "kind": "natural park buffer zone"}]
    verdict, reasons, _ = judge(change(area=20), big)
    assert verdict == "high_concern" and "protected_buffer" in codes(reasons)
    fire = records(inside=True, fire=True)
    fire["protected"]["areas"] = [{"name": "Parc X", "kind": "natural park buffer zone"}]
    assert judge(change(area=60, ctype="fire"), fire)[0] == "expected"


def test_mixed_zoning_uses_the_shares_and_no_zone_is_not_a_failure():
    mixed = records(zone="urban")
    mixed["zoning"]["shares"] = {"urban": 0.7, "non_buildable": 0.3}
    assert judge(change(area=1), mixed)[0] == "review"
    mostly_urban = records(zone="urban")
    mostly_urban["zoning"]["shares"] = {"urban": 0.9, "non_buildable": 0.1}
    assert "zoning_non_buildable" not in codes(judge(change(area=1), mostly_urban)[1])
    thin = records(zone="developable")
    thin["zoning"]["shares"] = {"developable": 0.3, "unknown": 0.7}
    assert "planned_sector" not in codes(judge(change(area=9), thin)[1])
    sea = judge(change(area=9), records(zone=None))
    assert "records_unavailable" not in codes(sea[1])


def official(**over):
    rec = {"checked": True, "source": "Test records", "url": "https://example.org/x",
           "assessment_required": True, "assessment_completed": False,
           "actions": [{"kind": "stop_order", "date": "2026-10-06", "text": "The agency called on the company to suspend.",
                        "source": "Agency release", "url": "https://example.org/stop"},
                       {"kind": "investigation", "date": "2026-10-29", "text": "Police opened a preliminary investigation."}]}
    rec.update(over)
    return {"official": rec}


def test_missing_required_assessment_on_a_big_clearing_is_high_concern():
    verdict, reasons, explain = judge(change(area=330), {**records(), **official()})
    assert verdict == "high_concern" and codes(reasons)[0] == "assessment_missing"
    assert {"official_stop_order", "official_investigation"} <= set(codes(reasons))
    stop = next(r for r in reasons if r["code"] == "official_stop_order")
    assert stop["text"].startswith("6 Oct 2026:") and stop["url"] == "https://example.org/stop"
    assert stop["effect"] == "raises"
    assert "assessment" in explain


def test_missing_assessment_on_a_mid_size_change_is_review_and_a_small_one_is_not_flagged():
    assert judge(change(area=3), {**records(zone="urban"), **official()})[0] == "review"
    assert judge(change(area=0.5), {**records(zone="urban"), **official()})[0] == "expected"
    assert judge(change(area=330, ctype="structure"), {**records(zone="urban"), **official()})[0] == "review"
    done = official(assessment_completed=True)
    assert judge(change(area=330), {**records(zone="urban"), **done})[0] == "review"  # no record explains it


def test_official_actions_without_the_key_change_nothing():
    assert judge(change(area=330), records(zone="urban"))[0] == "review"


def test_official_record_with_a_scope_applies_only_to_changes_inside_it():
    pytest.importorskip("shapely")
    square = lambda x0, y0, x1, y1: {  # noqa: E731
        "type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
    doc = {"version": 1, "default": {"official": {**official()["official"],
                                                    "scope": square(26.0, 64.8, 26.1, 64.9)}}}
    inside = records_for(doc, "a", square(26.04, 64.84, 26.05, 64.85))
    outside = records_for(doc, "b", square(25.0, 64.0, 25.1, 64.1))
    assert "official" in inside and "scope" not in inside["official"] and "official" not in outside
    assert records_for(doc, "c")["official"]["checked"] is True  # no geometry given: not filtered


def test_failed_lookups_are_counted_and_all_failed_writes_nothing(fixture_copy):
    path = fixture_copy / "fixture" / "changes.geojson"
    original = path.read_text(encoding="utf-8")

    def offline(geometry, change):
        return {k: {"source": k, "url": None, "checked": False, "error": "timeout"}
                for k in ("protected", "cadastre", "zoning", "solar")}

    with pytest.raises(SystemExit) as stop:
        apply_file(path, lookup=offline)
    assert "Nothing written" in str(stop.value) and path.read_text(encoding="utf-8") == original

    _, after, failed = apply_file(path, lookup=offline, allow_unchecked=True)
    assert failed["cadastre"] == 7 and sum(after.values()) == 7
    assert path.read_text(encoding="utf-8") != original

    def partly(geometry, change):
        recs = offline(geometry, change)
        recs["protected"] = {"source": "p", "url": None, "checked": True, "inside": False, "areas": []}
        return recs

    _, _, failed = apply_file(path, lookup=partly)
    assert failed == {"cadastre": 7, "zoning": 7, "solar": 7}
