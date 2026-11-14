"""Picture frames: grid, smoothing, fixed stretches, thinning and a tiny end-to-end radar run."""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from sarwatch import frames, pipeline

WINDOW = (26.02, 64.795, 26.20, 64.875)


def test_grid_is_north_up_about_700_wide_with_square_ground_pixels():
    t, w, h = frames.grid_for(WINDOW)
    assert w == 700 and 700 < h < 760
    assert t.a > 0 and t.e < 0 and t.c == pytest.approx(26.02) and t.f == pytest.approx(64.875)
    assert frames.corners(WINDOW) == [[26.02, 64.875], [26.2, 64.875], [26.2, 64.795], [26.02, 64.795]]


def test_smoothing_is_a_linear_mean_and_ignores_nan():
    p = np.full((7, 7), 1.0, np.float32)
    p[3, 3] = 10.0
    sm = frames.smooth_linear(p)
    assert sm[3, 3] == pytest.approx(2.0)          # (8 + 10) / 9
    p[0, 0] = np.nan
    assert frames.smooth_linear(p)[0, 1] == pytest.approx(1.0)
    assert np.isnan(frames.smooth_linear(np.full((5, 5), np.nan, np.float32))).all()


def test_radar_stretch_is_fixed():
    lo, hi = frames.RADAR_RANGE_DB
    g = frames.radar_stretch(np.array([lo - 5, lo, (lo + hi) / 2, hi, hi + 5, np.nan]))
    assert g.tolist() == [0, 0, 0.5, 1, 1, 0]


def test_photo_stretch_is_fixed_and_fills_gaps_grey():
    rgb = np.full((2, 2, 3), 0.1, np.float32)
    rgb[0, 0] = np.nan
    out = frames.photo_stretch(rgb)
    assert out.dtype == np.uint8 and out[0, 0].tolist() == [128, 128, 128]
    assert (frames.photo_stretch(np.full((1, 1, 3), 0.5)) == 255).all()


def test_thin_days_keeps_the_clearer_of_close_days():
    d0 = date(2026, 4, 1)
    cand = [(d0, 0.95, "a"), (d0 + timedelta(1), 0.99, "b"), (d0 + timedelta(5), 0.92, "c"), (d0, 0.91, "dup")]
    kept = frames.thin_days(cand, min_gap=3)
    assert [p for _, _, p in kept] == ["b", "c"]


def test_jpeg_steps_quality_down_to_fit():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (200, 200), dtype=np.uint8)
    big = frames.jpeg_bytes(img, 95, max_bytes=10**9)
    small = frames.jpeg_bytes(img, 95, max_bytes=len(big) // 2)
    assert len(small) < len(big)


def _fake_stack(root, days):
    """A tiny Sentinel-1 cache on the real Muhos UTM grid: a dark patch (lost vegetation) appears from 2026 on."""
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds

    x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:32635", *WINDOW)
    n = 60
    transform = from_bounds(x0, y0, x1, y1, n, n)
    cache = root / "muhos" / "s1"
    for i, day in enumerate(days):
        vh = np.full((n, n), 0.04, np.float32) * (1.0 + 0.5 * (i % 2))   # every other date is wetter: +1.8 dB
        if day.year >= 2026:
            vh[20:40, 20:40] = 0.004
        pipeline.save_frame(pipeline.cache_path(cache, day), pipeline.Frame(
            day=day, data={"VV": vh * 3, "VH": vh}, transform=tuple(transform)[:6], epsg=32635, bbox=WINDOW,
            source="fake", mb=None, seconds=0.0))


SUMMER = [date(2025, 6, 2) + timedelta(6 * i) for i in range(4)]


def test_time_average_is_1_2_1_and_skips_far_neighbours():
    stack = [np.full((2, 2), v, np.float32) for v in (1.0, 5.0, 1.0, 9.0)]
    days = [date(2026, 6, 1), date(2026, 6, 7), date(2026, 6, 13), date(2026, 9, 1)]
    out = frames.time_average(stack, days)
    assert out[1][0, 0] == pytest.approx((1 + 10 + 1) / 4)
    assert out[0][0, 0] == pytest.approx((2 + 5) / 3)       # no pass before
    assert out[3][0, 0] == pytest.approx(9.0)               # the snow gap: neighbour too far away


def test_radar_frames_end_to_end(tmp_path, monkeypatch):
    days = [date(2026, 6, 1) + timedelta(6 * i) for i in range(5)]
    _fake_stack(tmp_path / "stacks", SUMMER + days + [date(2026, 11, 3)])
    skip = pipeline._skip_spans(pipeline.SITES["muhos"])           # 3 Nov 2026 is a skipped (frozen) pass
    out = tmp_path / "frames" / "radar"
    listed = frames.radar_frames("muhos", tmp_path / "stacks", out, WINDOW, skip)
    assert [f["date"] for f in listed] == [d.isoformat() for d in SUMMER + days]
    assert all((out / f"{f['date']}.jpg").is_file() for f in listed)
    from PIL import Image
    imgs = {f["date"]: np.asarray(Image.open(out / f"{f['date']}.jpg").convert("RGB"), float) for f in listed}
    h, w, _ = imgs[SUMMER[0].isoformat()].shape
    assert w == 700
    centre, edge = (slice(h // 2 - 20, h // 2 + 20), slice(w // 2 - 20, w // 2 + 20)), (slice(5, 25), slice(5, 25))
    summer, late = imgs[SUMMER[1].isoformat()], imgs[days[4].isoformat()]
    # 2025: grey everywhere. 2026: the patch is pink (red and blue well above green); the edge stays grey on dry and wet dates
    assert np.abs(summer[centre][..., 0] - summer[centre][..., 2]).max() < 8
    assert (late[centre][..., 0] - late[centre][..., 1]).mean() > 60
    assert (late[centre][..., 2] - late[centre][..., 1]).mean() > 40
    assert np.abs(late[edge][..., 0] - late[edge][..., 2]).max() < 8


def test_small_patches_and_water_are_not_tinted():
    drop = np.zeros((40, 40), np.float32)
    drop[2:5, 2:5] = 5.0       # 9 px, far under 1 ha
    drop[10:35, 10:35] = 5.0   # 625 px
    base = np.full((40, 40), -14.0, np.float32)
    base[10:20, 10:35] = -25.0  # water
    alpha = frames.lost_alpha(drop, base, pixel_ha=0.0147)
    assert alpha[3, 3] == 0 and alpha[12, 12] == 0 and alpha[30, 30] > 0.8


def test_build_writes_frames_json_that_the_contract_accepts(tmp_path):
    from sarwatch.contract import validate

    days = SUMMER[:2] + [date(2026, 6, 1)]
    _fake_stack(tmp_path / "stacks", days)
    site_dir = tmp_path / "app" / "data" / "muhos"
    site_dir.mkdir(parents=True)
    doc = frames.build("muhos", tmp_path / "stacks", root=tmp_path, photos=False)
    assert [s["id"] for s in doc["sets"]] == ["radar"]
    saved = json.loads((site_dir / "frames.json").read_text(encoding="utf-8"))
    assert saved == doc and len(saved["coordinates"]) == 4
    errors = []
    from sarwatch import contract
    contract._check_frames(site_dir, errors)
    assert errors == [] and validate is not None
