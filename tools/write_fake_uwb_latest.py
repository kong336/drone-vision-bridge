#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def write_latest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write fake UWB/AOA latest JSON for dry-run bench testing.")
    parser.add_argument("--latest", default="/root/vision_comm/latest_uwb.json")
    parser.add_argument("--distance-m", type=float, default=3.2)
    parser.add_argument("--azimuth-deg", type=float, default=30.0)
    parser.add_argument("--elevation-deg", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=0.0, help="Keep refreshing for this many seconds. Default writes once.")
    parser.add_argument("--rate", type=float, default=5.0)
    args = parser.parse_args()

    path = Path(args.latest)
    started = time.time()
    count = 0
    while True:
        payload = {
            "ok": True,
            "cmd": "location",
            "distance_cm": int(round(args.distance_m * 100)),
            "distance_m": args.distance_m,
            "azimuth_deg": args.azimuth_deg,
            "elevation_deg": args.elevation_deg,
            "_received_time": time.time(),
        }
        write_latest(path, payload)
        count += 1
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        if args.seconds <= 0 or time.time() - started >= args.seconds:
            break
        time.sleep(max(0.02, 1.0 / max(args.rate, 0.1)))
    print(f"wrote {count} fake UWB sample(s) to {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
