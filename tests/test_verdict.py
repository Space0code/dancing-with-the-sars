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
        "solar": ok(plants=[{**pl, "located": True} for pl in plants]),  # a list with map positions (see the tests at the end)
    }
    if fire:
        out["fire"] = ok(recorded=True)
    out.update(over)
    return out


def plant(ha=12.0, status="Autoritzat"):
    return {"name": "Solar X", "status": status, "ha": ha, "ha_in_municipality": ha}


def change(area=10.0, ctype="clearing", explain="Radar saw the tree signal drop by -6 dB here.", confidence=None):
    props = {"id": "t-0001", "type": ctype, "area_ha": area, "first_date": "2026-03-01", "explain": explain}
    return {**props, "confidence": confidence} if confidence else props


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
        "fixture-0004": "expected", "fixture-0005": "expected", "fixture-0006": "high_concern",  # 0004: 1.2 ha, low conf.
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
    assert verdict == "expected" and codes(reasons)[0] == "small_area" and "No building registered" not in explain


def test_protected_buffer_zone_raises_but_a_thin_edge_overlap_is_neutral():
    buffer = records(inside=True, zone="urban", built=1)  # a building record would make this "expected"
    buffer["protected"]["areas"] = [{"name": "Parc X", "kind": "natural park buffer zone"}]
    verdict, reasons, _ = judge(change(area=3), buffer)
    assert verdict == "review" and codes(reasons)[0] == "protected_buffer"
    edge = records(inside=True, zone="urban", built=1)
    edge["protected"]["overlap_share"] = 0.05  # below 10 %: it only borders the area
    verdict, reasons, _ = judge(change(area=3), edge)
    assert verdict == "expected" and "protected_edge" in codes(reasons)
    assert next(r for r in reasons if r["code"] == "protected_edge")["effect"] == "neutral"
    assert "borders a protected area" in next(r for r in reasons if r["code"] == "protected_edge")["text"]
    edge["protected"]["overlap_share"] = 0.15  # a real overlap
    verdict, reasons, _ = judge(change(area=3), edge)
    assert verdict == "high_concern" and codes(reasons)[0] == "protected_area"
    edge["protected"]["overlap_share"] = None  # the service sent no outline: treated as a real overlap (safe side)
    assert judge(change(area=3), edge)[0] == "high_concern"
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
    no_steps = official(actions=[])  # only the missing assessment: too small and too uncertain to flag on its own
    uncertain = judge(change(area=0.5, confidence="low"), {**records(zone="urban"), **no_steps})
    assert uncertain[0] == "expected" and codes(uncertain[1])[0] == "small_uncertain"
    # an official step on record (a stop notice) is a different matter: it lifts even a small, uncertain change
    lifted = judge(change(area=0.5, confidence="low"), {**records(zone="urban"), **official()})
    assert lifted[0] == "review" and codes(lifted[1])[0] == "official_stop_order"
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


# ---- the seven `official` points and the two rule decisions (PR #31 re-review, #9) ----


def test_assessment_reason_uses_the_agreed_wording_per_change_type():
    texts = {
        ctype: judge(change(area=330, ctype=ctype), {**records(), **official()})[1][0]["text"]
        for ctype in ("clearing", "earthworks", "structure")
    }
    assert texts["clearing"] == "The required environmental assessment was not finished when this clearing happened."
    assert texts["earthworks"].endswith("when these earthworks happened.")
    assert texts["structure"].endswith("when this change happened.")


def test_a_record_without_scope_says_it_covers_the_whole_site():
    doc = {"version": 1, "default": {"official": {k: v for k, v in official()["official"].items()}}}
    recs = records_for(doc, "a")
    assert recs["official"]["site_wide"] is True
    text = judge(change(area=330), {**records(), **recs})[1][0]["text"]
    assert text.endswith("This record covers the whole site, not only this spot.")
    assert "whole site" not in judge(change(area=330), {**records(), **official()})[1][0]["text"]  # not marked
    doc_scoped = {"version": 1, "default": {"official": {**official()["official"], "scope": {
        "type": "Polygon", "coordinates": [[[0, 0], [0, 50], [50, 50], [50, 0], [0, 0]]]}}}}
    assert "site_wide" not in records_for(doc_scoped, "a", None)["official"]
    per_change = {"version": 1, "changes": {"a": {"official": official()["official"]}}}
    assert "site_wide" not in records_for(per_change, "a")["official"]


def test_two_official_actions_of_the_same_kind_and_date_both_show():
    twin = {"kind": "stop_order", "date": "2026-10-06", "text": "A second notice.", "source": "Agency"}
    rec = official()
    rec["official"]["actions"] = rec["official"]["actions"] + [twin]
    reasons = judge(change(area=330), {**records(), **rec})[1]
    assert codes(reasons).count("official_stop_order") == 2


def test_an_official_step_lifts_expected_to_needs_review_but_not_a_fire():
    acts = official(assessment_required=False)  # only the dated actions remain
    verdict, reasons, _ = judge(change(area=6, ctype="structure"), {**records(zone="urban", built=2), **acts})
    assert verdict == "review" and codes(reasons)[0] == "official_stop_order"
    assert "cadastre_building_found" in codes(reasons)  # the building record is still listed
    fire = judge(change(area=60, ctype="fire"), {**records(fire=True), **acts})
    assert fire[0] == "expected"
    assert judge(change(area=6, ctype="structure"), records(zone="urban", built=2))[0] == "expected"  # no record: no lift


def test_outside_spain_the_size_only_reason_does_not_blame_the_land_registry():
    na = {k: {"checked": False, "not_applicable": True} for k in ("protected", "cadastre", "zoning", "solar")}
    verdict, reasons, _ = judge(change(area=9), na)
    assert verdict == "review" and codes(reasons)[0] == "size_only"
    assert reasons[0]["text"].startswith("No public land records are connected for this country yet")
    assert "records_unavailable" not in codes(reasons)
    broken = {k: {"checked": False, "source": k, "url": None} for k in ("protected", "cadastre", "zoning", "solar")}
    assert "land registry could not be checked" in judge(change(area=9), broken)[1][0]["text"]


def test_a_scope_that_is_only_touched_at_the_border_is_outside():
    pytest.importorskip("shapely")
    square = lambda x0, y0, x1, y1: {  # noqa: E731
        "type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
    scope = square(26.0, 64.8, 26.1, 64.9)
    doc = {"version": 1, "default": {"official": {**official()["official"], "scope": scope}}}
    assert "official" not in records_for(doc, "a", square(26.1, 64.8, 26.2, 64.9))  # shares the eastern border only
    assert "official" in records_for(doc, "b", square(26.09, 64.8, 26.2, 64.9))  # really overlaps


def test_a_pending_solar_application_is_not_an_authorisation():
    pending = plant(ha=12, status="En tramitació")
    verdict, reasons, _ = judge(change(area=12), records(zone="urban", plants=[pending]))
    assert verdict == "review" and codes(reasons)[0] == "solar_application_pending"
    assert "being processed; it is not authorised yet" in reasons[0]["text"] and reasons[0]["effect"] == "raises"
    small = judge(change(area=1.5), records(zone="urban", plants=[plant(ha=1.5, status="En tramitació")]))
    assert small[0] == "review" and codes(small[1])[0] == "solar_application_pending"  # lifted although small
    for status in ("Autoritzat", "En servei", "Aprovat"):  # these do count
        assert judge(change(area=12), records(zone="urban", plants=[plant(status=status)]))[0] == "expected", status
    # an authorised plant or a building record still wins over a pending one
    both = judge(change(area=12), records(zone="urban", plants=[pending, plant(status="Autoritzat")]))
    assert both[0] == "expected" and "solar_application_pending" not in codes(both[1])


def test_a_half_developable_half_non_buildable_place_is_both_and_says_so():
    """Reviewer case (agroparc-0004): 51 % developable, 49 % non-buildable. Label stays review (row 5)."""
    recs = records(zone="developable")
    recs["zoning"]["shares"] = {"developable": 0.51, "non_buildable": 0.49}
    verdict, reasons, explain = judge(change(area=1.2, ctype="structure"), recs)
    assert verdict == "review" and codes(reasons)[0] == "zoning_non_buildable"
    assert "planned_sector" in codes(reasons) and "no_record_found" not in codes(reasons)  # a planned area is a match
    text = {r["code"]: r["text"] for r in reasons}
    assert text["zoning_non_buildable"] == "About 49 % of the place is zoned as non-buildable."
    assert text["planned_sector"] == "About 51 % of the place is inside a planned development area."
    plain = records(zone="non_buildable")
    plain["zoning"]["shares"] = {"non_buildable": 0.97}
    assert judge(change(area=1.2), plain)[1][0]["text"] == "The land is zoned as non-buildable."  # nearly all: plain


def test_building_and_solar_reasons_do_not_overclaim():
    """Reviewer: the registry dates buildings by year (so "since the change" can include older ones), and the solar
    list is by municipality only (so "here" is too exact)."""
    reasons = judge(change(area=9, ctype="structure"), records(zone="urban", built=4))[1]
    text = next(r["text"] for r in reasons if r["code"] == "cadastre_building_found")
    assert text.startswith("4 building(s) registered here date from 2026 or later") and "construction years only" in text
    pending = judge(change(area=12), records(zone="urban", plants=[plant(status="En tramitació")]))[1]
    solar = next(r["text"] for r in pending if r["code"] == "solar_application_pending")
    assert "in this municipality" in solar and "no exact location" in solar and "here" not in solar.split("in this")[0][-6:]
    no_date = {k: v for k, v in change(area=9, ctype="structure").items() if k != "first_date"}
    assert "since the change" in next(
        r["text"] for r in judge(no_date, records(zone="urban", built=1))[1] if r["code"] == "cadastre_building_found")


def test_no_record_reason_does_not_overclaim_about_the_registry():
    reasons = judge(change(area=9), records(zone="urban"))[1]
    text = next(r["text"] for r in reasons if r["code"] == "no_record_found")
    assert "months late" in text and "since the change" in text and "No registered building" not in text


def test_a_buffer_zone_never_counts_toward_the_real_overlap_share():
    """Reviewer case: the buffer zone covers the whole change, a real area only 2 % of it."""
    recs = records(inside=True, zone="urban", built=1)
    recs["protected"]["areas"] = [
        {"name": "Parc buffer", "kind": "natural park buffer zone", "overlap_share": 1.0},
        {"name": "Riu", "kind": "PEIN", "overlap_share": 0.02},
    ]
    recs["protected"].update(overlap_share=1.0, core_overlap_share=0.02)
    verdict, reasons, _ = judge(change(area=3), recs)
    assert verdict == "expected" and "protected_edge" in codes(reasons)  # the real part only borders
    assert "Parc buffer" not in next(r for r in reasons if r["code"] == "protected_edge")["text"]
    recs["protected"]["core_overlap_share"] = 0.5  # a real overlap: high concern, and the text names the real area
    verdict, reasons, _ = judge(change(area=3), recs)
    assert verdict == "high_concern" and "Riu" in reasons[0]["text"] and "Parc buffer" not in reasons[0]["text"]
    # hand-entered records that only know ``overlap_share`` still work
    old = records(inside=True, zone="urban", built=1)
    old["protected"]["overlap_share"] = 0.05
    assert judge(change(area=3), old)[0] == "expected"


def test_rerunning_a_change_without_a_radar_sentence_is_identical():
    first = judge(change(area=9, explain=None), records(zone="urban"))
    judged = {**change(area=9, explain=first[2]), "reasons": first[1]}
    again = judge(judged, records(zone="urban"))
    assert again[2] == first[2] and first[2].count(first[1][0]["text"]) == 1


def test_bad_input_gives_a_clear_error_or_is_skipped_not_a_crash():
    for bad in (None, 0, -1, float("nan"), "x"):
        with pytest.raises(ValueError, match="area_ha must be a positive number"):
            judge({**change(), "area_ha": bad}, records())
    with pytest.raises(ValueError, match="area_ha"):
        judge({k: v for k, v in change().items() if k != "area_ha"}, records())
    rec = official()
    rec["official"]["actions"] = ["a stray string", None] + rec["official"]["actions"]
    assert codes(judge(change(area=330), {**records(), **rec})[1]).count("official_stop_order") == 1
    stringy = records(zone="urban", plants=[{"name": "X", "status": "Autoritzat", "ha": "12", "ha_in_municipality": "12.0"}])
    assert judge(change(area=12), stringy)[0] == "expected"
    zero = records(zone="urban", plants=[{"name": "X", "status": "Autoritzat", "ha": 5, "ha_in_municipality": 0}])
    assert judge(change(area=12), zero)[0] == "review"  # 0 ha in this municipality is a value, not "missing"
    junk = records(zone="urban", plants=[{"name": "X", "status": None, "ha": "n/a"}])
    assert judge(change(area=12), junk)[0] == "review"


def test_a_bad_scope_gives_a_clear_error():
    pytest.importorskip("shapely")
    doc = {"version": 1, "default": {"official": {**official()["official"], "scope": {"type": "Foo", "coordinates": []}}}}
    with pytest.raises(ValueError, match="scope must be a GeoJSON Polygon or MultiPolygon"):
        records_for(doc, "a", {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})


def test_no_output_ever_accuses_anyone_whatever_the_combination():
    import itertools

    banned = ("illegal", "unlawful", "violat", "guilty", "crime", "offence")
    base = {
        "protected": [None, {"inside": True, "areas": [{"name": "Parc X", "kind": "PEIN"}]}],
        "zoning": [None, "non_buildable", "urban"],
        "built": [0, 2],
        "plants": [(), (plant(status="En tramitació"),), (plant(),)],
        "fire": [False, True],
        "off": [None, official()],
    }
    seen = 0
    for prot, zone, built, plants, fire, off in itertools.product(*base.values()):
        recs = records(zone=zone, built=built, plants=plants, fire=fire, inside=bool(prot))
        if prot:
            recs["protected"]["areas"] = prot["areas"]
        if off:
            recs.update(off)
        for ch in (change(area=0.8, confidence="low"), change(area=3, ctype="structure"), change(area=40, ctype="earthworks")):
            verdict, reasons, explain = judge(ch, recs)
            blob = json.dumps([reasons, explain]).lower()
            assert not any(word in blob for word in banned), blob
            assert reasons[0]["text"] in explain
            seen += 1
    assert seen == 2 * 3 * 2 * 3 * 2 * 2 * 3  # every combination ran


def test_small_low_confidence_changes_are_not_flagged_on_their_own():
    verdict, reasons, explain = judge(change(area=1.2, confidence="low"), records(zone="non_buildable"))
    assert verdict == "expected" and codes(reasons)[0] == "small_uncertain"
    assert "too small" in reasons[0]["text"] and "too uncertain to flag on its own" in reasons[0]["text"]
    assert "is fine" not in explain and "illegal" not in explain.lower()
    # the same change with medium confidence, or 2 ha and up, is still flagged
    assert judge(change(area=1.2, confidence="medium"), records(zone="non_buildable"))[0] == "review"
    assert judge(change(area=2.0, confidence="low"), records(zone="non_buildable"))[0] == "review"
    # a protected area is not a "flag on its own by size": it stays high concern
    assert judge(change(area=0.9, confidence="low"), records(inside=True))[0] == "high_concern"
    # a building record or a fire still explains it: no change of label
    assert judge(change(area=1.2, confidence="low"), records(zone="urban", built=1))[0] == "expected"


# ---- Muhos final run: scope without the size floor, the change's own sensor, small forestry without records ----


def _no_records():
    return {k: {"checked": False, "not_applicable": True} for k in ("protected", "cadastre", "zoning", "solar")}


def _scoped_official():
    return {"version": 1, "default": {"official": {**official()["official"], "scope": {
        "type": "Polygon", "coordinates": [[[0, 0], [0, 50], [50, 50], [50, 0], [0, 0]]]}}}}


def test_inside_the_records_scope_the_size_floor_does_not_apply():
    inside = records_for(_scoped_official(), "a", {"type": "Point", "coordinates": [10, 10]})
    assert inside["official"]["in_scope"] is True
    small = judge(change(area=3.8), {**_no_records(), **inside})
    assert small[0] == "high_concern" and codes(small[1])[0] == "assessment_missing"
    # the same 3.8 ha with a record that covers the whole site (no scope) keeps the limits: only "review"
    whole_site = records_for({"version": 1, "default": {"official": official()["official"]}}, "a")
    assert "in_scope" not in whole_site["official"]
    assert judge(change(area=3.8), {**_no_records(), **whole_site})[0] == "review"
    # a tiny low-confidence change inside the scope still follows the record, it is not "too small"
    assert judge(change(area=0.4, confidence="low"), {**_no_records(), **inside})[0] == "high_concern"
    # clearings and earthworks only: a structure inside the scope is "review", as before
    assert judge(change(area=3.8, ctype="structure"), {**_no_records(), **inside})[0] == "review"


def test_the_size_reason_names_the_changes_own_sensor():
    na = _no_records()
    optical = {**change(area=9, ctype="other"), "sensor": "OPERA DIST-ALERT"}
    assert judge(optical, na)[1][0]["source"] == "NASA optical alerts (Landsat + Sentinel-2)"
    assert judge({**change(area=9, ctype="other"), "sensor": "Sentinel-1 C-band"}, na)[1][0]["source"] == "Sentinel-1 C-band"
    assert judge(change(area=9, ctype="other"), na)[1][0]["source"] == "Satellite detection"
    small = judge({**change(area=0.5), "sensor": "NISAR L-band"}, records(zone="urban"))
    assert [r["source"] for r in small[1] if r["code"] == "small_area"] == ["NISAR L-band"]


def test_a_small_clearing_without_land_records_is_expected_not_review():
    verdict, reasons, _ = judge({**change(area=3.2), "sensor": "OPERA DIST-ALERT"}, _no_records())
    assert verdict == "expected" and codes(reasons)[0] == "small_no_records" and reasons[0]["effect"] == "lowers"
    assert "too small to flag on its own" in reasons[0]["text"] and "no official record we have covers this spot" in reasons[0]["text"]
    assert "records_unavailable" not in codes(reasons)
    # a big clearing, or any other kind of change, is still flagged by size alone
    assert judge(change(area=6), _no_records())[0] == "review"
    assert judge(change(area=3.2, ctype="other"), _no_records())[0] == "review"
    # where the land registry answers (Catalonia) nothing changes: no record -> needs review
    assert judge(change(area=3.2), records(zone="urban"))[0] == "review"
    # a protected area still raises it
    assert judge(change(area=3.2), {**_no_records(), **records(inside=True)})[0] == "high_concern"


# ---- PR #107 review: the new reason must not contradict an official record or repeat itself; sliver and boundaries ----


def _box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0, y1], [x1, y1], [x1, y0], [x0, y0]]]}


def test_small_no_records_is_not_used_when_an_official_record_applies_to_the_change():
    recs = records_for({"version": 1, "default": {"official": official()["official"]}}, "x", None)  # site-wide record
    verdict, reasons, _ = judge(change(area=1.5), {**_no_records(), **recs})
    assert "small_no_records" not in codes(reasons)
    done = official(assessment_completed=True)  # a completed assessment is still a record that covers this spot
    assert "small_no_records" not in codes(judge(change(area=1.5), {**_no_records(), **done})[1])


def test_a_small_clearing_without_records_names_its_size_only_once():
    for conf in (None, "low"):
        _, reasons, _ = judge(change(area=1.99, confidence=conf), _no_records())
        assert codes(reasons)[0] == "small_no_records"
        assert not {"small_area", "small_uncertain"} & set(codes(reasons))


def test_small_no_records_boundaries_are_5_ha_exclusive_and_any_size_below():
    assert judge(change(area=4.99), _no_records())[1][0]["code"] == "small_no_records"
    assert judge(change(area=2.0), _no_records())[1][0]["code"] == "small_no_records"
    assert judge(change(area=5.0), _no_records())[1][0]["code"] == "size_only"


def test_a_sliver_inside_the_scope_does_not_lift_the_size_floor():
    doc = _scoped_official()
    doc["default"]["official"]["scope"] = _box(0, 0, 1, 1)
    mostly = records_for(doc, "a", _box(0.2, 0.2, 1.2, 1.2))   # 64 % inside
    sliver = records_for(doc, "b", _box(0.99, 0.0, 1.99, 1.0))  # 1 % inside
    touching = records_for(doc, "c", _box(1.0, 0.0, 2.0, 1.0))  # shares only a border
    assert mostly["official"]["in_scope"] is True
    assert "official" in sliver and "in_scope" not in sliver["official"]
    assert "official" not in touching
    assert judge(change(area=3.8), {**_no_records(), **mostly})[0] == "high_concern"
    assert judge(change(area=3.8), {**_no_records(), **sliver})[0] == "review"


def test_zoning_without_a_developable_share_is_not_a_planned_area_just_because_the_zone_says_so():
    mixed = ok(zone="developable", shares={"non_buildable": 0.3, "urban": 0.7})
    verdict, reasons, _ = judge(change(area=12, ctype="earthworks"), records(zone="developable", zoning=mixed))
    assert "planned_sector" not in codes(reasons)
    alone = judge(change(area=12, ctype="earthworks"), records(zoning=ok(zone="developable")))  # no shares at all
    assert "planned_sector" in codes(alone[1])


# ---- Barcelona: port and airport land, late starts ----


def system_rec(kind="port", share=0.9):
    return {"system": ok(system=kind, shares={kind: share})}


def test_a_structure_on_port_land_is_expected_even_when_the_zoning_says_non_buildable():
    verdict, reasons, _ = judge(change(area=23, ctype="structure"),
                                {**records(zone="non_buildable"), **system_rec()})
    assert verdict == "expected" and codes(reasons)[0] == "system_land"
    assert reasons[0]["effect"] == "lowers" and "port system land" in reasons[0]["text"]
    assert "zoning_non_buildable" in codes(reasons)  # still listed: the card shows both records
    air = judge(change(area=9, ctype="earthworks"), {**records(zone="urban"), **system_rec("airport")})
    assert air[0] == "expected" and "airport system land" in air[1][0]["text"]


def test_port_land_does_not_hide_a_protected_area_or_a_buffer_zone():
    assert judge(change(area=8), {**records(inside=True), **system_rec()})[0] == "high_concern"
    buffer = {"protected": ok(inside=True, areas=[{"name": "Delta", "kind": "Natura 2000 buffer zone"}])}
    assert judge(change(area=8), {**records(), **buffer, **system_rec()})[0] == "review"


def test_port_land_needs_most_of_the_change_and_a_change_type_works_can_explain():
    assert judge(change(area=8, ctype="structure"), {**records(zone="urban"), **system_rec(share=0.4)})[0] == "review"
    assert judge(change(area=8, ctype="other"), {**records(zone="urban"), **system_rec()})[0] == "review"
    assert judge(change(area=8), {**records(zone="urban"), "system": ok(system=None, shares={})})[0] == "review"
    assert judge(change(area=8), records(zone="urban"))[0] == "review"  # no system record at all: as before


def test_a_failed_port_lookup_is_reported_and_changes_nothing_else():
    failed = {"system": {"source": "MUC", "url": None, "checked": False, "error": "boom"}}
    verdict, reasons, _ = judge(change(area=8), {**records(zone="urban"), **failed})
    assert verdict == "review" and any("port and airport land map could not be checked" in r["text"] for r in reasons)


def late(**kw):
    return {**change(**kw), "sources": [{"role": "late_start"}, {"role": "not_watching"}]}


def test_a_late_start_counts_only_dated_buildings_from_three_years_before_the_sensor_began():
    old = {"cadastre": ok(buildings=3, built_since=0, undated=0)}  # three buildings, all older than that
    dated = judge(change(area=8), {**records(zone="urban"), **old})
    assert dated[0] == "review" and "No building registered since the change" in dated[1][0]["text"]
    none = judge(late(area=8), {**records(zone="urban"), **old})
    assert none[0] == "review" and none[1][0]["text"].startswith("No building registered here is from the years")
    assert "since the change" not in none[1][0]["text"] and "cannot date this change" in none[1][0]["text"]
    recent = judge(late(area=8), {**records(zone="urban"), "cadastre": ok(buildings=3, built_since=1, undated=0)})
    assert recent[0] == "expected" and codes(recent[1])[0] == "cadastre_building_found"
    assert "date from 2023 or later" in recent[1][0]["text"]  # first date in 2026: three years of lead
    # a building with no year explains nothing: the label follows the remaining rules (here: no record, needs review)
    undated = judge(late(area=8), {**records(zone="urban"), "cadastre": ok(buildings=1, built_since=0, undated=1)})
    assert undated[0] == "review" and "cadastre_building_found" not in codes(undated[1])
    # zoning and protected areas still apply to a late start
    assert judge(late(area=8), {**records(zone="non_buildable"), **old})[1][0]["code"] == "zoning_non_buildable"
    assert judge(late(area=8), {**records(inside=True), **old})[0] == "high_concern"
    # a source that detected the change dates it: not a late start, the plain rule applies
    dated_by_one = {**late(area=8), "sources": [{"role": "late_start"}, {"role": "detected"}]}
    assert judge(dated_by_one, {**records(zone="urban"), **old})[0] == "review"


def test_late_start_lookups_get_a_three_year_lead(monkeypatch):
    from sarwatch import verdict

    seen = {}
    monkeypatch.setattr("sarwatch.context.lookup_all", lambda g, since=None, until=None: seen.update(since=since, until=until) or {})
    verdict.run_lookups({"type": "Point", "coordinates": [0, 0]}, {**late(area=8), "first_date": "2016-06-05"})
    assert seen == {"since": "2013-01-01", "until": "2016-06-05"}
    verdict.run_lookups({"type": "Point", "coordinates": [0, 0]}, {**change(area=8), "first_date": "2016-06-05"})
    assert seen == {"since": "2016-06-05", "until": "2016-06-05"}


def test_port_land_needs_80_percent_and_hides_the_municipal_solar_plant():
    assert judge(change(area=8), {**records(zone="urban"), **system_rec(share=0.7)})[0] == "review"
    plants = [plant(ha=17.3)]
    verdict, reasons, explain = judge(change(area=23), {**records(zone="non_buildable", plants=plants), **system_rec(share=0.97)})
    assert verdict == "expected" and codes(reasons)[0] == "system_land" and "solar_plant_listed" not in codes(reasons)
    assert "solar plant" not in explain
    assert "solar_plant_listed" in codes(judge(change(area=23), {**records(zone="urban", plants=plants)})[1])  # elsewhere it stays


def test_a_protected_area_is_named_once_and_a_missing_share_does_not_crash():
    twin = {"protected": ok(inside=True, areas=[{"name": "Delta del Llobregat", "kind": "PEIN"},
                                                {"name": "Delta del Llobregat", "kind": "Natura 2000"}])}
    assert judge(change(area=8), {**records(), **twin})[1][0]["text"].count("Delta del Llobregat") == 1
    nones = {"system": ok(system="port", shares={"port": None})}
    assert judge(change(area=8), {**records(zone="urban"), **nones})[0] == "review"


# ---- a solar list without positions cannot explain a change (Catalan list: municipality only) ----


def test_plants_without_a_location_add_no_reason_and_decide_nothing():
    unlocated = {"solar": ok(plants=[{"name": "Solar X", "status": "Autoritzat", "ha": 17.3, "ha_in_municipality": 17.3},
                                     {"name": "Solar Y", "status": "En tramitació", "ha": 9.0}])}
    verdict, reasons, _ = judge(change(area=12), {**records(zone="urban"), **unlocated})
    assert verdict == "review" and codes(reasons)[0] == "no_record_found"
    assert not {"solar_plant_listed", "solar_application_pending", "solar_plant_other"} & set(codes(reasons))
    # the same plants with a position behave as before
    located = {"solar": ok(plants=[{"name": "Solar X", "status": "Autoritzat", "ha": 17.3, "located": True}])}
    assert judge(change(area=12), {**records(zone="urban"), **located})[0] == "expected"
