"""Command line: ``streamwatch {fetch,benchmark,watch}``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from .detectors import REGISTRY
from .evaluate import PROBATION, tune_and_test
from .nab import DATA_DIR, fetch, load_group


def benchmark(data_dir: Path, out_dir: Path | None, detectors: list[str]) -> dict:
    groups = {g: load_group(g, data_dir) for g in ("realKnownCause", "realAWSCloudwatch")}
    results = {}
    for tune_g, test_g in (
        ("realAWSCloudwatch", "realKnownCause"),
        ("realKnownCause", "realAWSCloudwatch"),
    ):
        key = f"tune on {tune_g} -> test on {test_g}"
        results[key] = [tune_and_test(d, groups[tune_g], groups[test_g]) for d in detectors]
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (out_dir / "results.md").write_text(to_markdown(results), encoding="utf-8")
    return results


def to_markdown(results: dict) -> str:
    lines = []
    for split, rows in results.items():
        lines += [
            f"### {split}",
            "",
            "| Detector | Threshold | Tune F1 | Windows detected | Recall | Alerts | Precision "
            "| F1 | Median delay | Points/s |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r['detector']} | {r['threshold']} | {r['tune_f1']} | "
                f"{r['test_detected']}/{r['test_windows']} | {r['test_recall']} | "
                f"{r['test_alerts']} | {r['test_precision']} | {r['test_f1']} | "
                f"{r['test_median_delay']} | {r['points_per_second']:,} |"
            )
        lines.append("")
    return "\n".join(lines)


def watch(path: Path, detector: str, threshold: float) -> int:
    """Replay a CSV (timestamp,value) as a stream and print alerts as they happen."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    det = REGISTRY[detector]()
    start = int(len(rows) * PROBATION)
    alerts = 0
    for i, row in enumerate(rows):
        ts = datetime.fromisoformat(row["timestamp"].split(".")[0])
        score = det.update(ts, float(row["value"]))
        if i >= start and score >= threshold:
            alerts += 1
            print(f"{ts.isoformat()} value={row['value']} score={score:.1f} ALERT")
    print(f"{alerts} alert points over {len(rows)} readings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="streamwatch", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download NAB series and labels (pinned commit)")
    f.add_argument("--data-dir", type=Path, default=DATA_DIR)
    b = sub.add_parser("benchmark", help="tune on one NAB group, test on the other")
    b.add_argument("--data-dir", type=Path, default=DATA_DIR)
    b.add_argument("--out", type=Path, default=Path("reports"))
    b.add_argument("--detectors", nargs="+", default=list(REGISTRY), choices=list(REGISTRY))
    w = sub.add_parser("watch", help="stream one CSV through a detector")
    w.add_argument("csv", type=Path)
    w.add_argument("--detector", default="ensemble", choices=list(REGISTRY))
    w.add_argument("--threshold", type=float, default=5.0)
    args = parser.parse_args(argv)

    if args.cmd == "fetch":
        print(f"downloaded {fetch(args.data_dir)} files into {args.data_dir}")
    elif args.cmd == "benchmark":
        print(to_markdown(benchmark(args.data_dir, args.out, args.detectors)))
    else:
        return watch(args.csv, args.detector, args.threshold)
    return 0


if __name__ == "__main__":
    sys.exit(main())
