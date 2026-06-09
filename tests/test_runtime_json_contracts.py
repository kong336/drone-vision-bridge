from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_validator(schema: str, payload: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        payload_path = Path(handle.name)
    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "validate_json_file.py"),
                "--schema",
                str(ROOT / "schemas" / schema),
                str(payload_path),
            ],
            check=True,
        )
    finally:
        payload_path.unlink(missing_ok=True)


def test_vision_latest_schema() -> None:
    run_validator(
        "vision_latest.schema.json",
        {
            "status": "ok",
            "valid": True,
            "fps": 24.0,
            "target": {
                "class": "wrench",
                "conf": 0.96,
                "distance_m": 0.4,
                "offset": {"dx": 4, "dy": 0},
                "position_camera_m": {
                    "x": 0.003,
                    "y": 0.0,
                    "z": 0.4,
                    "frame": "camera",
                    "method": "pinhole_fov_estimate",
                },
            },
            "detections": [{}],
            "_received": {"from": "127.0.0.1", "port": 5005, "time": 1780569000.0},
        },
    )


def test_vision_latest_schema_allows_no_target() -> None:
    run_validator(
        "vision_latest.schema.json",
        {
            "status": "ok",
            "valid": False,
            "fps": 20.64,
            "target": None,
            "distance_m": 0.708,
            "distance_method": "depth_grid_center",
            "depth_age": 0.132,
        },
    )


def test_mission_decision_schema() -> None:
    run_validator(
        "mission_decision.schema.json",
        {
            "time": 1780569000.0,
            "state": "GRAB_DRY_RUN",
            "reason": "target is stably within dry-run grab distance",
            "command": {"arm": "would_grab"},
            "context": {"vision_lock_count": 8, "centered_count": 8, "grab_ready_count": 8},
            "vision": {"ok": True, "age_sec": 0.1, "class": "wrench", "conf": 0.96, "distance_m": 0.4, "dx": 4, "dy": 0},
            "uwb": {"ok": False, "age_sec": None, "distance_m": None, "azimuth_deg": None, "elevation_deg": None},
            "flight": {"ok": True, "age_sec": 0.1, "armed": False, "system_status": 3},
        },
    )


def test_arm_action_schema() -> None:
    run_validator(
        "arm_action.schema.json",
        {
            "time": 1780569000.0,
            "arm_dry_run": {
                "mode": "blocked_requires_enable_file",
                "reason": "stable grab decision present, but manipulator dry-run enable file is missing",
                "age_sec": 0.1,
                "enable_file": "/root/vision_comm/ENABLE_ARM_DRY_RUN",
                "target": {"class": "wrench", "conf": 0.96, "distance_m": 0.4, "dx": 4, "dy": 0},
            },
        },
    )


def test_uwb_aoa_schema() -> None:
    run_validator(
        "uwb_aoa.schema.json",
        {
            "ok": True,
            "cmd": "location",
            "version": 1,
            "sequence_id": 1,
            "anchor_id": 10,
            "tag_id": 20,
            "distance_cm": 98,
            "distance_m": 0.98,
            "azimuth_deg": -39,
            "elevation_deg": 13,
            "tag_status": 0,
            "batch_sn": 1,
            "checksum": 82,
            "_received_time": 1780569000.0,
        },
    )


def main() -> int:
    tests = [
        test_vision_latest_schema,
        test_vision_latest_schema_allows_no_target,
        test_mission_decision_schema,
        test_arm_action_schema,
        test_uwb_aoa_schema,
    ]
    for test in tests:
        test()
        print(f"OK {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
