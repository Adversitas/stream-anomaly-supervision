import json
import math
import random
from datetime import datetime, timedelta

import pytest

from streamwatch.cli import benchmark, main
from streamwatch.detectors import REGISTRY, EWMAControl, RobustMAD, RollingZ, SeasonalProfile
from streamwatch.evaluate import Counts, alerts_from_scores, evaluate_alerts, tune_and_test
from streamwatch.nab import SERIES, Series, load_series

T0 = datetime(2024, 1, 1)


def make_series(n=2000, spike_at=1500, name="synthetic/spike", seasonal=False, seed=0):
    rng = random.Random(seed)
    ts = [T0 + timedelta(minutes=30 * i) for i in range(n)]
    values = []
    for i, t in enumerate(ts):
        base = 100 + (40 * math.sin(2 * math.pi * t.hour / 24) if seasonal else 0)
        values.append(base + rng.gauss(0, 2) + (60 if spike_at <= i < spike_at + 3 else 0))
    window = (ts[spike_at - 10], ts[spike_at + 20])
    return Series(name, ts, values, [window])


@pytest.mark.parametrize("key", list(REGISTRY))
def test_every_detector_flags_a_spike(key):
    s = make_series()
    det = REGISTRY[key]()
    scores = [det.update(t, x) for t, x in zip(s.timestamps, s.values, strict=True)]
    assert max(scores[1500:1503]) > 5 * max(1.0, sorted(scores[400:1400])[int(0.5 * 1000)])


def test_detectors_are_causal():
    """Changing a future point must not change past scores."""
    s = make_series()
    a, b = RollingZ(), RollingZ()
    future = list(s.values)
    future[1999] = 1e6
    sa = [a.update(t, x) for t, x in zip(s.timestamps, s.values, strict=True)]
    sb = [b.update(t, x) for t, x in zip(s.timestamps, future, strict=True)]
    assert sa[:1999] == sb[:1999]


def test_flat_signal_does_not_divide_by_zero():
    det = RobustMAD(window=50)
    scores = [det.update(T0, 5.0) for _ in range(100)]
    assert all(math.isfinite(x) for x in scores) and max(scores) == 0


def test_ewma_tracks_level_shift():
    det = EWMAControl(alpha=0.05)
    for _ in range(300):
        det.update(T0, 10.0 + random.Random(1).gauss(0, 0.1))
    first = det.update(T0, 20.0)
    for _ in range(300):
        last = det.update(T0, 20.0)
    assert first > 10 and last < 1


def test_seasonal_profile_beats_global_on_daily_cycle():
    s = make_series(n=24 * 2 * 21, spike_at=24 * 2 * 18, seasonal=True)
    seasonal, glob = SeasonalProfile(), RollingZ()
    ss = [seasonal.update(t, x) for t, x in zip(s.timestamps, s.values, strict=True)]
    gs = [glob.update(t, x) for t, x in zip(s.timestamps, s.values, strict=True)]
    i = 24 * 2 * 18
    # signal-to-noise: spike score relative to the 99th percentile of normal scores
    normal = slice(24 * 2 * 15, i - 50)

    def ratio(scores):
        quiet = sorted(scores[normal])
        return max(scores[i : i + 3]) / quiet[int(0.99 * len(quiet))]

    assert ratio(ss) > ratio(gs)


def test_alerts_respect_probation_and_cooldown():
    scores = [10.0] * 1000
    alerts = alerts_from_scores(scores, threshold=5)
    assert alerts[0] == 150  # 15 % probation
    assert all(b - a == 11 for a, b in zip(alerts, alerts[1:], strict=False))  # 1 % cooldown + 1


def test_evaluate_alerts_counts():
    s = make_series()
    c = evaluate_alerts(s, [1495, 1700])
    assert (c.windows, c.detected, c.alerts, c.useful_alerts) == (1, 1, 2, 1)
    assert c.precision == 0.5 and c.recall == 1.0 and c.f1 == pytest.approx(2 / 3)
    assert 0 < c.median_delay < 1


def test_windows_inside_probation_are_ignored():
    s = make_series(spike_at=100)
    assert evaluate_alerts(s, []).windows == 0


def test_counts_accumulate():
    a, b = Counts(1, 1, 2, 1, [0.2]), Counts(2, 0, 3, 0, [])
    a += b
    assert (a.windows, a.detected, a.alerts, a.useful_alerts, a.delays) == (3, 1, 5, 1, [0.2])


def test_tune_and_test_reports_held_out_metrics():
    tune = [make_series(seed=i, name=f"t/{i}") for i in range(3)]
    test = [make_series(seed=10 + i, name=f"x/{i}") for i in range(2)]
    r = tune_and_test("rolling_z", tune, test)
    assert r["test_windows"] == 2 and r["test_recall"] == 1.0 and r["test_precision"] > 0.5


def write_nab_fixture(root):
    labels = {}
    for group, names in SERIES.items():
        for k, name in enumerate(names):
            s = make_series(n=600, spike_at=450, seed=k)
            (root / group).mkdir(parents=True, exist_ok=True)
            with open(root / group / f"{name}.csv", "w", encoding="utf-8") as fh:
                fh.write("timestamp,value\n")
                for t, x in zip(s.timestamps, s.values, strict=True):
                    fh.write(f"{t:%Y-%m-%d %H:%M:%S},{x:.3f}\n")
            a, b = s.windows[0]
            labels[f"{group}/{name}.csv"] = [
                [f"{a:%Y-%m-%d %H:%M:%S}.000000", f"{b:%Y-%m-%d %H:%M:%S}.000000"]
            ]
    (root / "combined_windows.json").write_text(json.dumps(labels), encoding="utf-8")


def test_load_series_and_benchmark_on_fixture(tmp_path):
    write_nab_fixture(tmp_path)
    s = load_series("realKnownCause", "nyc_taxi", tmp_path)
    assert len(s.values) == 600 and len(s.windows) == 1
    res = benchmark(tmp_path, tmp_path / "out", ["rolling_z", "ewma"])
    assert len(res) == 2 and (tmp_path / "out" / "results.md").exists()
    row = next(iter(res.values()))[0]
    assert row["test_recall"] > 0.8


def test_cli_watch(tmp_path, capsys):
    write_nab_fixture(tmp_path)
    path = tmp_path / "realKnownCause" / "nyc_taxi.csv"
    assert main(["watch", str(path), "--detector", "rolling_z", "--threshold", "6"]) == 0
    out = capsys.readouterr().out
    assert "ALERT" in out and "readings" in out
