"""Online anomaly detectors: one ``update(timestamp, value) -> score`` call per point.

Every detector is causal: the score of point *t* only uses points before *t*, so they can run
in a real-time supervision loop with bounded memory. Scores are on a z-like scale (larger = more
anomalous), so a single threshold family applies to all of them.
"""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime
from statistics import median

EPS = 1e-9


class Detector:
    name = "base"

    def update(self, ts: datetime, x: float) -> float:  # pragma: no cover - interface
        raise NotImplementedError


class RollingZ(Detector):
    """|x - mean| / std over the last ``window`` points (running sums, O(1) per point)."""

    name = "rolling z-score"

    def __init__(self, window: int = 288) -> None:
        self.window = window
        self.buf: deque[float] = deque()
        self.s = 0.0
        self.s2 = 0.0

    def update(self, ts: datetime, x: float) -> float:
        n = len(self.buf)
        score = 0.0
        if n >= 10:
            mean = self.s / n
            var = max(self.s2 / n - mean * mean, 0.0)
            score = abs(x - mean) / (math.sqrt(var) + EPS)
        self.buf.append(x)
        self.s += x
        self.s2 += x * x
        if len(self.buf) > self.window:
            old = self.buf.popleft()
            self.s -= old
            self.s2 -= old * old
        return score


class EWMAControl(Detector):
    """EWMA control chart: exponentially weighted mean and variance."""

    name = "EWMA control chart"

    def __init__(self, alpha: float = 0.02) -> None:
        self.alpha = alpha
        self.mean: float | None = None
        self.var = 0.0
        self.n = 0

    def update(self, ts: datetime, x: float) -> float:
        self.n += 1
        if self.mean is None:
            self.mean = x
            return 0.0
        diff = x - self.mean
        score = abs(diff) / (math.sqrt(self.var) + EPS) if self.n > 10 else 0.0
        incr = self.alpha * diff
        self.mean += incr
        self.var = (1 - self.alpha) * (self.var + diff * incr)
        return score


class RobustMAD(Detector):
    """|x - median| / (1.4826 * MAD) over a sliding window: insensitive to past spikes."""

    name = "rolling median / MAD"

    def __init__(self, window: int = 288) -> None:
        self.buf: deque[float] = deque(maxlen=window)

    def update(self, ts: datetime, x: float) -> float:
        score = 0.0
        if len(self.buf) >= 10:
            med = median(self.buf)
            mad = median(abs(v - med) for v in self.buf)
            scale = 1.4826 * mad
            if scale < EPS:  # flat signal: fall back to the range of the window
                scale = (max(self.buf) - min(self.buf)) / 4 + EPS
            score = abs(x - med) / scale
        self.buf.append(x)
        return score


class SeasonalProfile(Detector):
    """Residual against a per-(weekday, hour) EWMA profile: models daily and weekly cycles.

    Useful for business metrics (taxi demand, request counts) where "high" depends on the time
    of day. The score is the residual divided by the bucket's EWMA deviation.
    """

    name = "seasonal profile (weekday x hour)"

    def __init__(self, alpha: float = 0.1, min_obs: int = 3) -> None:
        self.alpha = alpha
        self.min_obs = min_obs
        self.mean: dict[tuple[int, int], float] = {}
        self.dev: dict[tuple[int, int], float] = {}
        self.count: dict[tuple[int, int], int] = {}
        self.global_dev = RollingZ(window=500)

    def update(self, ts: datetime, x: float) -> float:
        key = (ts.weekday(), ts.hour)
        fallback = self.global_dev.update(ts, x)
        if self.count.get(key, 0) < self.min_obs:
            score = fallback
        else:
            score = abs(x - self.mean[key]) / (self.dev[key] + EPS)
        if key not in self.mean:
            self.mean[key], self.dev[key], self.count[key] = x, 0.0, 1
        else:
            resid = abs(x - self.mean[key])
            self.mean[key] += self.alpha * (x - self.mean[key])
            self.dev[key] += self.alpha * (resid - self.dev[key])
            self.count[key] += 1
        return score


class Ensemble(Detector):
    """Median of the member scores: an alert needs agreement from most detectors."""

    name = "ensemble (median of 4)"

    def __init__(self) -> None:
        self.members = [RollingZ(), EWMAControl(), RobustMAD(), SeasonalProfile()]

    def update(self, ts: datetime, x: float) -> float:
        return float(median(m.update(ts, x) for m in self.members))


REGISTRY = {
    "rolling_z": RollingZ,
    "ewma": EWMAControl,
    "mad": RobustMAD,
    "seasonal": SeasonalProfile,
    "ensemble": Ensemble,
}
