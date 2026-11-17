"""Numenta Anomaly Benchmark (NAB) access: series + labelled anomaly windows.

Data are fetched from a pinned commit of github.com/numenta/NAB (MIT licence), not committed.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

NAB_COMMIT = "ea702d75cc2258d9d7dd35ca8e5e2539d71f3140"
BASE = f"https://raw.githubusercontent.com/numenta/NAB/{NAB_COMMIT}"
DATA_DIR = Path("data") / "nab"

SERIES = {
    "realKnownCause": [
        "ambient_temperature_system_failure",
        "cpu_utilization_asg_misconfiguration",
        "ec2_request_latency_system_failure",
        "machine_temperature_system_failure",
        "nyc_taxi",
        "rogue_agent_key_hold",
        "rogue_agent_key_updown",
    ],
    "realAWSCloudwatch": [
        "ec2_cpu_utilization_24ae8d",
        "ec2_cpu_utilization_53ea38",
        "ec2_cpu_utilization_5f5533",
        "ec2_cpu_utilization_77c1ca",
        "ec2_cpu_utilization_825cc2",
        "ec2_cpu_utilization_ac20cd",
        "ec2_cpu_utilization_fe7f93",
        "ec2_disk_write_bytes_1ef3de",
        "ec2_disk_write_bytes_c0d644",
        "ec2_network_in_257a54",
        "ec2_network_in_5abac7",
        "elb_request_count_8c0756",
        "grok_asg_anomaly",
        "iio_us-east-1_i-a2eb1cd9_NetworkIn",
        "rds_cpu_utilization_cc0c53",
        "rds_cpu_utilization_e47b3b",
    ],
}


@dataclass
class Series:
    name: str
    timestamps: list[datetime]
    values: list[float]
    windows: list[tuple[datetime, datetime]]


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text.strip().split(".")[0])


def fetch(data_dir: Path = DATA_DIR) -> int:
    data_dir = Path(data_dir)
    targets = [("labels/combined_windows.json", data_dir / "combined_windows.json")]
    for group, names in SERIES.items():
        targets += [(f"data/{group}/{n}.csv", data_dir / group / f"{n}.csv") for n in names]
    downloaded = 0
    for remote, local in targets:
        if local.exists():
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"{BASE}/{remote}", local)  # noqa: S310 - pinned https URL
        downloaded += 1
    return downloaded


def load_series(group: str, name: str, data_dir: Path = DATA_DIR) -> Series:
    data_dir = Path(data_dir)
    with open(data_dir / group / f"{name}.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    labels = json.loads((data_dir / "combined_windows.json").read_text(encoding="utf-8"))
    windows = [(_parse_ts(a), _parse_ts(b)) for a, b in labels.get(f"{group}/{name}.csv", [])]
    return Series(
        name=f"{group}/{name}",
        timestamps=[_parse_ts(r["timestamp"]) for r in rows],
        values=[float(r["value"]) for r in rows],
        windows=windows,
    )


def load_group(group: str, data_dir: Path = DATA_DIR) -> list[Series]:
    return [load_series(group, n, data_dir) for n in SERIES[group]]
