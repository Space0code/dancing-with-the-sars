"""Tests for the multi-sensor merge (kb/multi-sensor-design.md sections 1-4, 7)."""
from datetime import date as D

import pytest
from shapely.geometry import box

from sarwatch.merge import Detection, SiteSource, merge_detections, same_change

LON, LAT = 25.9, 64.8


def sq(x0, y0, w, h=None):
    """Box in lon/lat offsets (degrees) from the test site."""
    return box(LON + x0, LAT + y0, LON + x0 + w, LAT + y0 + (h or w))


def det(source, kind, poly, first, last=None, conf="medium", typ="clearing", nb=None, late=False, area=None):
    return Detection(source=source, kind=kind, polygon=poly, type=typ, first_date=first, last_date=last or first,
                     confidence=conf, not_before=nb, late_start=late, area_ha=area)


OPT = SiteSource("Optical alert", "optical", D(2023, 1, 1), sees=frozenset({"clearing"}),
                 risky_months=frozenset({11, 12, 1, 2}))
S1 = SiteSource("Sentinel-1", "radar", D(2016, 1, 1), revisit_days=12, risky_months=frozenset({11, 12, 1, 2, 3, 4}))
NISAR = SiteSource("NISAR", "radar", D(2026, 6, 25), revisit_days=12, risky_months=frozenset({11, 12, 1, 2, 3, 4}))
SITE = [OPT, S1, NISAR]


def roles(c):
    return {e["sensor"]: e["role"] for e in c.sources}


# ---------------------------------------------------------------- pairwise test

def test_same_change_needs_mutual_overlap_and_time():
    a = det("A", "optical", sq(0, 0, 0.01), D(2026, 5, 20), nb=D(2026, 5, 2))
    b = det("B", "radar", sq(0.002, 0, 0.01), D(2026, 5, 26), nb=D(2026, 5, 14))
    assert same_change(a, b)
    far = det("B", "radar", sq(0.002, 0, 0.01), D(2027, 5, 26), nb=D(2027, 5, 14))
    assert not same_change(a, far)  # same place, a year later
    apart = det("B", "radar", sq(0.5, 0, 0.01), D(2026, 5, 26), nb=D(2026, 5, 14))
    assert not same_change(a, apart)


def test_source_never_merges_with_itself():
    a = det("S1", "radar", sq(0, 0, 0.01), D(2026, 5, 20))
    b = det("S1", "radar", sq(0, 0, 0.01), D(2026, 5, 21))
    assert not same_change(a, b)
    assert len(merge_detections([a, b], SITE)) == 2


def test_type_is_not_tested():
    a = det("A", "optical", sq(0, 0, 0.01), D(2026, 5, 20), typ="clearing")
    b = det("B", "radar", sq(0, 0, 0.01), D(2026, 5, 22), typ="structure")
    assert same_change(a, b)


# ---------------------------------------------------------------- worked examples

def muhos():
    return [
        det("Optical alert", "optical", sq(0, 0, 0.0100, 0.0140), D(2026, 5, 20), nb=D(2026, 5, 2), area=14),
        det("Sentinel-1", "radar", sq(0.001, 0.001, 0.0100, 0.0100), D(2026, 5, 26), nb=D(2026, 5, 14), area=11),
        det("NISAR", "radar", sq(0.0005, 0.0005, 0.0100, 0.0120), D(2026, 6, 25), D(2026, 7, 10), late=True, area=13),
    ]


def test_muhos_clear_cut():
    (c,) = merge_detections(muhos(), SITE)
    assert (c.first_date, c.not_before, c.last_date) == (D(2026, 5, 20), D(2026, 5, 2), D(2026, 7, 10))
    assert c.sensor == "Optical alert"
    assert c.when == "between 2 and 20 May 2026"
    assert c.confidence == "high"  # medium + 1: optical and radar agree
    assert c.confidence_note == "Two independent kinds of satellite saw it"
    assert c.type == "clearing"
    assert roles(c) == {"Optical alert": "detected", "Sentinel-1": "detected", "NISAR": "late_start"}
    assert [e["sensor"] for e in c.sources] == ["Optical alert", "Sentinel-1", "NISAR"]
    s1 = c.sources[1]
    assert s1["note"] == "Sentinel-1 radar saw the same change, through clouds, on 26 May 2026."
    assert s1["not_before"] == "2026-05-14"  # kept as the source's own value, not used to tighten the change
    assert c.sources[0]["note"] == "An optical alert found vegetation loss here between 2 and 20 May 2026."
    assert c.sources[2]["note"] == "NISAR began watching on 25 Jun 2026 and shows the change already under way."
    assert c.sources[2]["not_before"] is None
    assert [e["area_ha"] for e in c.sources] == [14, 11, 13]
    assert c.area_ha >= 14 and all(0 < e["share"] <= 1 for e in c.sources)


def test_late_start_only_never_a_single_day():
    d = det("NISAR", "radar", sq(0, 0, 0.01), D(2026, 6, 25), late=True)
    (c,) = merge_detections([d], SITE)
    assert c.not_before is None and c.late_start_only
    assert c.when == "already under way on 25 Jun 2026, when NISAR began watching; the start date is not known"
    assert "happened" not in c.when and "cleared" not in c.when


def test_catalonia_warehouse():
    cat = [SiteSource("Optical alert", "optical", D(2023, 1, 1), sees=frozenset({"clearing"})),
           SiteSource("Sentinel-1", "radar", D(2016, 1, 1)),
           SiteSource("NISAR", "radar", D(2026, 6, 25))]
    d = det("Sentinel-1", "radar", sq(0, 0, 0.0075), D(2021, 3, 15), D(2021, 6, 20), typ="structure", nb=D(2021, 3, 3),
            area=6)
    (c,) = merge_detections([d], cat)
    assert c.type == "structure" and c.confidence == "medium"
    assert c.when == "between 3 and 15 Mar 2021"
    assert (c.first_date, c.not_before, c.last_date) == (D(2021, 3, 15), D(2021, 3, 3), D(2021, 6, 20))
    assert c.confidence_note == "Only Sentinel-1 radar was watching in 2021"
    assert roles(c) == {"Sentinel-1": "detected", "Optical alert": "not_watching", "NISAR": "not_watching"}
    notes = {e["sensor"]: e["note"] for e in c.sources}
    assert notes["Optical alert"] == "Optical alerts start in 2023."
    assert notes["NISAR"] == "NISAR was not flying yet."
    assert all(e["share"] is None and e["confidence"] is None for e in c.sources if e["role"] == "not_watching")


# ---------------------------------------------------------------- other rules

def test_same_place_changing_twice_is_two_changes():
    a = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2023, 5, 20), nb=D(2023, 5, 8))
    b = det("Optical alert", "optical", sq(0, 0, 0.01), D(2023, 5, 22))
    c = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2025, 8, 10), nb=D(2025, 7, 29))
    d = det("Optical alert", "optical", sq(0, 0, 0.01), D(2025, 8, 12))
    out = merge_detections([a, b, c, d], SITE)
    assert len(out) == 2
    assert [x.first_date.year for x in out] == [2023, 2025]


def test_nested_stay_separate_and_cite_each_other():
    big = det("Optical alert", "optical", sq(0, 0, 0.02, 0.04), D(2026, 6, 20), nb=D(2026, 6, 1), area=60)
    small = det("Sentinel-1", "radar", sq(0.005, 0.005, 0.005, 0.008), D(2026, 6, 24), nb=D(2026, 6, 12), conf="low")
    # overlap: 100 % of small but only ~5 % of big -> not mutual
    assert not same_change(big, small)
    out = {c.sensor: c for c in merge_detections([big, small], SITE)}
    assert len(out) == 2
    s, b = out["Sentinel-1"], out["Optical alert"]
    sm = next(e for e in s.sources if e["sensor"] == "Optical alert")
    bg = next(e for e in b.sources if e["sensor"] == "Sentinel-1")
    assert sm["share"] == pytest.approx(1.0, abs=0.01) and sm["role"] == "detected"
    assert "lies inside a larger optical alert area" in sm["note"]
    assert 0.03 < bg["share"] < 0.1 and bg["note"].startswith("Sentinel-1 saw ") and "of it" in bg["note"]
    assert s.confidence == "medium" and s.confidence_note == "Two independent kinds of satellite saw it"  # low + 1
    assert b.confidence == "medium" and b.confidence_note == "Only Optical alert saw it"  # nothing gained


def test_single_source_risky_month_loses_a_step():
    d = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 1, 15), nb=D(2026, 1, 3), conf="medium")
    (c,) = merge_detections([d], SITE)
    assert c.confidence == "low"
    assert c.confidence_note.startswith("Seen only by radar while the ground was probably frozen or snow-covered")
    d2 = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 6, 15), nb=D(2026, 6, 3), conf="medium")
    assert merge_detections([d2], SITE)[0].confidence == "medium"


def test_confidence_clamped():
    d = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 1, 15), conf="low")
    assert merge_detections([d], SITE)[0].confidence == "low"


def test_two_radars_agree():
    a = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 7, 1), nb=D(2026, 6, 19))
    b = det("NISAR", "radar", sq(0, 0, 0.01), D(2026, 7, 8), nb=D(2026, 6, 26))
    (c,) = merge_detections([a, b], SITE)
    assert c.confidence == "high" and c.confidence_note == "Both radar satellites saw it"
    assert roles(c)["Optical alert"] == "not_seen"
    assert c.sources[-1]["note"] == "The optical alerts did not flag it."
    # in a risky month two radars lose a step instead
    a2 = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2027, 1, 7), nb=D(2026, 12, 26))
    b2 = det("NISAR", "radar", sq(0, 0, 0.01), D(2027, 1, 12), nb=D(2027, 1, 1))
    assert merge_detections([a2, b2], SITE)[0].confidence == "low"


def test_structure_not_flagged_by_optical_says_why_and_type_tiebreak():
    a = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 7, 1), typ="structure")
    b = det("NISAR", "radar", sq(0, 0, 0.01), D(2026, 7, 5), typ="clearing")
    (c,) = merge_detections([a, b], SITE)
    assert c.type == "structure"
    assert "only see clearing" in c.sources[-1]["note"]


def test_unknown_not_before_reads_on_or_before():
    d = det("Sentinel-1", "radar", sq(0, 0, 0.01), D(2026, 7, 1))
    assert merge_detections([d], SITE)[0].when == "on or before 1 Jul 2026"
