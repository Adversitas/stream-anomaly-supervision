"""Window-based evaluation, as an on-call team experiences it.

* scores are computed point by point (causal);
* the first 15 % of each series is a probationary period (no alerting), as in NAB;
* an alert mutes the detector for a cooldown (1 % of the series length) so that one incident
  produces one page, not hundreds;
* an anomaly window is **detected** if at least one alert falls inside it (recall);
* an alert is **useful** if it falls inside a window (precision);
* the **delay** is the time from window start to the first alert, as a share of window length.

Thresholds are tuned on one NAB group and reported on the other, so no number comes from
in-sample tuning.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .detectors import REGISTRY
from .nab import Series

PROBATION = 0.15
COOLDOWN = 0.01
THRESHOLDS = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0]


@dataclass
class Counts:
    windows: int = 0
    detected: int = 0
    alerts: int = 0
    useful_alerts: int = 0
    delays: list[float] = field(default_factory=list)

    def __iadd__(self, other: Counts) -> Counts:
        self.windows += other.windows
        self.detected += other.detected
        self.alerts += other.alerts
        self.useful_alerts += other.useful_alerts
        self.delays += other.delays
        return self

    @property
    def recall(self) -> float:
        return self.detected / self.windows if self.windows else 0.0

    @property
    def precision(self) -> float:
        return self.useful_alerts / self.alerts if self.alerts else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def median_delay(self) -> float:
        if not self.delays:
            return float("nan")
        d = sorted(self.delays)
        return d[len(d) // 2]


def score_series(detector_key: str, series: Series) -> tuple[list[float], float]:
    det = REGISTRY[detector_key]()
    start = time.perf_counter()
    scores = [det.update(t, x) for t, x in zip(series.timestamps, series.values, strict=True)]
    return scores, time.perf_counter() - start


def alerts_from_scores(scores: list[float], threshold: float) -> list[int]:
    n = len(scores)
    start = int(n * PROBATION)
    cooldown = max(1, int(n * COOLDOWN))
    alerts, muted_until = [], -1
    for i in range(start, n):
        if i > muted_until and scores[i] >= threshold:
            alerts.append(i)
            muted_until = i + cooldown
    return alerts


def evaluate_alerts(series: Series, alerts: list[int]) -> Counts:
    n = len(series.timestamps)
    probation_end = series.timestamps[int(n * PROBATION)]
    windows = [(a, b) for a, b in series.windows if b > probation_end]
    c = Counts(windows=len(windows), alerts=len(alerts))
    alert_ts = [series.timestamps[i] for i in alerts]
    c.useful_alerts = sum(any(a <= t <= b for a, b in windows) for t in alert_ts)
    for a, b in windows:
        inside = [t for t in alert_ts if a <= t <= b]
        if inside:
            c.detected += 1
            span = (b - a).total_seconds() or 1.0
            c.delays.append((inside[0] - a).total_seconds() / span)
    return c


def pooled(scored: dict[str, list[float]], series: list[Series], threshold: float) -> Counts:
    total = Counts()
    for s in series:
        total += evaluate_alerts(s, alerts_from_scores(scored[s.name], threshold))
    return total


def tune_and_test(
    detector_key: str, tune: list[Series], test: list[Series]
) -> dict[str, float | str]:
    scored, seconds, points = {}, 0.0, 0
    for s in tune + test:
        scored[s.name], dt = score_series(detector_key, s)
        seconds += dt
        points += len(s.values)
    best = max(THRESHOLDS, key=lambda th: (pooled(scored, tune, th).f1, th))
    tuned, held_out = pooled(scored, tune, best), pooled(scored, test, best)
    return {
        "detector": REGISTRY[detector_key].name,
        "threshold": best,
        "tune_f1": round(tuned.f1, 3),
        "test_windows": held_out.windows,
        "test_detected": held_out.detected,
        "test_recall": round(held_out.recall, 3),
        "test_alerts": held_out.alerts,
        "test_precision": round(held_out.precision, 3),
        "test_f1": round(held_out.f1, 3),
        "test_median_delay": round(held_out.median_delay, 3),
        "points_per_second": round(points / seconds) if seconds else 0,
    }
