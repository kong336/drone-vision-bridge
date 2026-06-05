#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    for attempt in range(5):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        except PermissionError:
            if attempt == 4:
                return None
            time.sleep(0.05)
    return None


def decision_age(decision: dict[str, Any]) -> float | None:
    timestamp = decision.get("time")
    if timestamp is None:
        return None
    return time.time() - float(timestamp)


def map_decision_to_arm(decision: dict[str, Any], max_age: float, enable_file: Path | None = None) -> dict[str, Any]:
    age = decision_age(decision)
    state = decision.get("state")
    command = decision.get("command") or {}
    vision = decision.get("vision") or {}

    if age is None or age > max_age:
        return {"mode": "hold", "reason": "decision stale or missing timestamp", "age_sec": age}

    if state == "GRAB_DRY_RUN" and enable_file is not None and not enable_file.exists():
        return {
            "mode": "blocked_requires_enable_file",
            "reason": "stable grab decision present, but manipulator dry-run enable file is missing",
            "enable_file": str(enable_file),
            "age_sec": round(age, 3),
            "target": {
                "class": vision.get("class"),
                "conf": vision.get("conf"),
                "distance_m": vision.get("distance_m"),
                "dx": vision.get("dx"),
                "dy": vision.get("dy"),
            },
        }

    if state == "GRAB_DRY_RUN":
        return {
            "mode": "would_close_gripper",
            "reason": "state machine confirmed stable target in grab range",
            "age_sec": round(age, 3),
            "target": {
                "class": vision.get("class"),
                "conf": vision.get("conf"),
                "distance_m": vision.get("distance_m"),
                "dx": vision.get("dx"),
                "dy": vision.get("dy"),
            },
        }

    if state in {"VISION_LOCK", "FINE_ALIGN", "GRAB_READY"}:
        return {
            "mode": "track_only",
            "reason": f"state={state}; no gripper action",
            "age_sec": round(age, 3),
            "state_command": command,
        }

    if state == "FAILSAFE":
        return {"mode": "failsafe_hold", "reason": decision.get("reason"), "age_sec": round(age, 3)}

    return {"mode": "hold", "reason": f"state={state}", "age_sec": round(age, 3)}


def replace_with_retry(tmp: Path, path: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run manipulator monitor. It never drives servos.")
    parser.add_argument("--decision-latest", default="/root/vision_comm/latest_decision.json")
    parser.add_argument("--action-latest", default=None, help="Optionally write latest dry-run arm action JSON to this path.")
    parser.add_argument("--enable-file", default="/root/vision_comm/ENABLE_ARM_DRY_RUN", help="File that must exist before GRAB_DRY_RUN maps to would_close_gripper. Set empty string to disable this guard.")
    parser.add_argument("--period", type=float, default=0.2)
    parser.add_argument("--max-age", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    path = Path(args.decision_latest)
    action_path = Path(args.action_latest) if args.action_latest else None
    enable_file = Path(args.enable_file) if args.enable_file else None
    while True:
        decision = read_json(path)
        if decision is None:
            action = {"mode": "hold", "reason": "missing decision file"}
        else:
            action = map_decision_to_arm(decision, args.max_age, enable_file)
        report = {"time": round(time.time(), 3), "arm_dry_run": action}
        if action_path is not None:
            action_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = action_path.with_name(f"{action_path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            replace_with_retry(tmp, action_path)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if args.once:
            break
        time.sleep(args.period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
