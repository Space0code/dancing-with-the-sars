"""Synthetic tests for sarwatch.change: inject a known change into speckle and get it back."""
from datetime import date, timedelta

import numpy as np

from sarwatch.change import ChangeParams, detect_changes

N_PASSES, NY, NX = 12, 120, 160
PIXEL_M = (10.0, 10.0)  # one pixel = 0.01 ha
DATES = [date(2026, 6, 1) + timedelta(days=12 * i) for i in range(N_PASSES)]
HH_MEAN, HV_MEAN = 0.1, 0.02  # -10 dB and -17 dB
RECT = (slice(30, 70), slice(40, 100))  # 40 x 60 px = 24 ha
RECT_HA = 24.0
CHANGE_PASS = 5


def speckle(rng, mean, looks=16, passes=N_PASSES):
    """A (time, y, x) stack of uniform ground with `looks`-look speckle: gamma noise with the given mean."""
    return rng.gamma(looks, mean / looks, size=(passes, NY, NX)).astype(np.float32)


def scene(seed=0, passes=N_PASSES):
    rng = np.random.default_rng(seed)
    return {"HH": speckle(rng, HH_MEAN, passes=passes), "HV": speckle(rng, HV_MEAN, passes=passes)}


def gain(db):
    return 10 ** (db / 10)


def truth_mask(*windows):
    mask = np.zeros((NY, NX), dtype=bool)
    for window in windows:
        mask[window] = True
    return mask


def iou(a, b):
    return (a & b).sum() / (a | b).sum()


def test_clearing_is_found_placed_dated_and_typed():
    stack = scene()
    stack["HV"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)

    result = detect_changes(stack, DATES, PIXEL_M)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "clearing"
    assert iou(result.labels == region.label, truth_mask(RECT)) >= 0.7
    assert abs(region.area_ha - RECT_HA) <= 0.2 * RECT_HA
    assert abs(DATES.index(region.first_date) - CHANGE_PASS) <= 1
    assert abs(DATES.index(region.last_date) - CHANGE_PASS) <= 1
    assert region.signal["metric"] == "HV_dB"
    assert abs(region.signal["delta"] + 6) < 0.5
    assert abs(region.signal["after"] - region.signal["before"] - region.signal["delta"]) < 1e-9
    assert region.confidence == "high"
    assert region.series["dates"] == DATES
    assert len(region.series["HV_dB"]) == len(region.series["HH_dB"]) == N_PASSES
    row0, col0, row1, col1 = region.bbox
    inside = np.zeros((NY, NX), dtype=bool)
    inside[row0:row1, col0:col1] = True
    assert not (result.labels == region.label)[~inside].any()

    changed = result.labels > 0
    assert result.labels.dtype == np.int32 and result.first_change_idx.dtype == np.int16
    assert result.delta_db["HV"].dtype == np.float32 and result.delta_db["HV"].shape == (NY, NX)
    assert (result.first_change_idx[changed] == CHANGE_PASS).all()
    assert (result.first_change_idx[~changed] == -1).all()


def test_structure_is_typed_from_copol_rise():
    stack = scene(1)
    stack["HH"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(8)

    result = detect_changes(stack, DATES, PIXEL_M)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "structure"
    assert region.signal["metric"] == "HH_dB"
    assert region.signal["delta"] > 6
    assert iou(result.labels == region.label, truth_mask(RECT)) >= 0.7
    assert abs(DATES.index(region.first_date) - CHANGE_PASS) <= 1


def test_pure_speckle_gives_no_regions():
    result = detect_changes(scene(2), DATES, PIXEL_M)

    assert result.regions == []
    assert not result.labels.any()
    assert (result.first_change_idx == -1).all()


def test_region_below_min_area_is_dropped():
    stack = scene(3)
    tiny = (slice(50, 57), slice(80, 87))  # 7 x 7 px = 0.49 ha, under the 0.5 ha default
    stack["HV"][CHANGE_PASS:][(slice(None), *tiny)] *= gain(-6)

    assert detect_changes(stack, DATES, PIXEL_M).regions == []
    kept = detect_changes(stack, DATES, PIXEL_M, ChangeParams(min_area_ha=0.1))
    assert len(kept.regions) == 1
    assert (kept.labels > 0)[tiny].any() and not (kept.labels > 0)[~truth_mask(tiny)].any()


def test_invalid_pixels_never_become_regions():
    stack = scene(4)
    stack["HV"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)
    masked = (slice(90, 115), slice(110, 150))  # a real change, but outside the caller's valid mask
    stack["HV"][CHANGE_PASS:][(slice(None), *masked)] *= gain(-6)
    valid = ~truth_mask(masked)
    no_data = (slice(25, 45), slice(30, 55))  # NaN in every pass, overlapping a corner of the clearing
    zeros = (slice(60, 80), slice(90, 110))   # zero power in every pass, overlapping another corner
    for arr in stack.values():
        arr[(slice(None), *no_data)] = np.nan
        arr[(slice(None), *zeros)] = 0.0
        arr[7, :, 120:] = np.nan              # one pass with a missing strip
        arr[2, 10, 10] = -1.0                 # a stray negative sample

    result = detect_changes(stack, DATES, PIXEL_M, valid=valid)

    unusable = truth_mask(masked, no_data, zeros)
    assert not result.labels[unusable].any()
    assert (result.first_change_idx[unusable] == -1).all()
    assert all(np.isnan(delta[unusable]).all() for delta in result.delta_db.values())
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "clearing"
    assert iou(result.labels == region.label, truth_mask(RECT) & ~unusable) >= 0.7
    assert np.isfinite(region.series["HV_dB"]).all()


def test_single_polarization_stack():
    rng = np.random.default_rng(5)
    vh = speckle(rng, HV_MEAN)
    vh[CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)

    result = detect_changes({"VH": vh}, DATES, PIXEL_M)

    assert list(result.delta_db) == ["VH"]
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "clearing"
    assert region.signal["metric"] == "VH_dB"
    assert set(region.series) == {"dates", "VH_dB"}


def test_change_going_both_ways_is_earthworks():
    stack = scene(6)
    rows, cols = RECT
    stack["HV"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)                           # vegetation stripped
    stack["HH"][CHANGE_PASS:, rows, cols.start:70] *= gain(8)                             # rough fill: brighter
    stack["HH"][CHANGE_PASS:, rows, 70:cols.stop] *= gain(-8)                             # graded flat: darker

    result = detect_changes(stack, DATES, PIXEL_M)

    assert len(result.regions) == 1
    assert result.regions[0].type == "earthworks"
    assert iou(result.labels == 1, truth_mask(RECT)) >= 0.7


def test_erratic_change_is_earthworks():
    stack = scene(7)
    offsets_db = [0, 0, 0, 0, 6, 0, 7, 1, 8, 2, 7, 6]  # ends 6 dB up, but never settles
    for t, offset in enumerate(offsets_db):
        stack["HH"][t][RECT] *= gain(offset)

    result = detect_changes(stack, DATES, PIXEL_M)

    assert len(result.regions) == 1
    assert result.regions[0].type == "earthworks"


def test_change_in_the_last_pass_is_dated_there():
    stack = scene(8)
    last = N_PASSES - 1
    stack["HV"][last][RECT] *= gain(-6)

    result = detect_changes(stack, DATES, PIXEL_M, ChangeParams(n_late=1))

    assert len(result.regions) == 1
    assert result.regions[0].first_date == result.regions[0].last_date == DATES[last]
    assert (result.first_change_idx[result.labels > 0] == last).all()


def test_regions_are_sorted_by_area_and_labelled_in_that_order():
    stack = scene(9)
    small = (slice(85, 105), slice(110, 135))  # 20 x 25 px = 5 ha
    stack["HV"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)
    stack["HH"][8:][(slice(None), *small)] *= gain(8)

    result = detect_changes(stack, DATES, PIXEL_M)

    assert [r.type for r in result.regions] == ["clearing", "structure"]
    assert [r.label for r in result.regions] == [1, 2]
    assert result.regions[0].area_ha > result.regions[1].area_ha
    assert [DATES.index(r.first_date) for r in result.regions] == [CHANGE_PASS, 8]
    assert (result.labels == 2)[small].any() and not (result.labels == 2)[RECT].any()


def test_a_few_stray_pixels_do_not_turn_a_clearing_into_earthworks():
    stack = scene(10)
    stack["HV"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-6)
    stack["HH"][CHANGE_PASS:, 40:45, 50:55] *= gain(8)   # a small bright pile of logs
    stack["HH"][CHANGE_PASS:, 53:61, 82:90] *= gain(-8)  # a small puddle (bigger: the boxcar dilutes a drop)

    result = detect_changes(stack, DATES, PIXEL_M)

    assert len(result.regions) == 1
    assert result.regions[0].type == "clearing"


def test_lower_threshold_still_names_a_weaker_cband_clearing():
    rng = np.random.default_rng(11)
    stack = {"VV": speckle(rng, HH_MEAN), "VH": speckle(rng, HV_MEAN)}
    stack["VH"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(-2.5)  # C-band sees less of the canopy

    result = detect_changes(stack, DATES, PIXEL_M, ChangeParams(threshold_db=2.0))

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "clearing" and region.signal["metric"] == "VH_dB"
    assert iou(result.labels == region.label, truth_mask(RECT)) >= 0.7


def test_erratic_change_after_a_long_quiet_baseline_is_earthworks():
    passes = 30
    dates = [date(2024, 1, 1) + timedelta(days=12 * i) for i in range(passes)]
    stack = scene(12, passes)
    offsets_db = [0] * 18 + [6, 1, 7, 2, 8, 1, 7, 2, 6, 1, 7, 6]  # 18 quiet passes, then the ground is reworked
    for t, offset in enumerate(offsets_db):
        stack["HH"][t][RECT] *= gain(offset)

    result = detect_changes(stack, dates, PIXEL_M)

    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.type == "earthworks"
    assert 18 <= dates.index(region.first_date) <= 20


def test_normalize_and_hold_drop_a_wet_spell_but_keep_a_lasting_change():
    """Rain over 2 of the 3 late passes: the whole scene +2 dB, a bare field +5 dB. A real change: +6 dB co-pol from
    CHANGE_PASS on. Only the lasting change may survive the seasonal guards."""
    stack = scene()
    field = (slice(80, 110), slice(20, 70))  # 30 x 50 px = 15 ha
    for pol in stack:
        stack[pol][-3:-1] *= gain(2)
    stack["HH"][-3:-1][(slice(None), *field)] *= gain(3)
    stack["HH"][CHANGE_PASS:][(slice(None), *RECT)] *= gain(6)
    rect, wet = truth_mask(RECT), truth_mask(field)

    plain = detect_changes(stack, DATES, PIXEL_M)
    assert any((plain.labels == r.label)[wet].any() for r in plain.regions)  # the wet field is a false alarm

    guarded = detect_changes(stack, DATES, PIXEL_M, ChangeParams(normalize=True, hold=True))
    assert len(guarded.regions) == 1
    region = guarded.regions[0]
    assert region.type == "structure"
    assert iou(guarded.labels == region.label, rect) >= 0.7
    assert abs(region.signal["delta"] - 6) < 0.7  # the series are normalized too, the step keeps its true size
    assert abs(DATES.index(region.first_date) - CHANGE_PASS) <= 1


def test_normalize_is_off_by_default_and_removes_a_scene_wide_shift():
    stack = scene()
    for pol in stack:
        stack[pol][-3:] *= gain(4)  # a calibration step or a soaking rain over the whole window
    assert len(detect_changes(stack, DATES, PIXEL_M).regions) >= 1
    assert detect_changes(stack, DATES, PIXEL_M, ChangeParams(normalize=True)).regions == []
