from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_preflight(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "mp257" / "preflight_check.py"),
            "--root",
            str(root),
            "--schemas-dir",
            str(ROOT / "schemas"),
            "--arm-servo-config",
            str(ROOT / "mp257" / "arm_servo_config.example.json"),
            *extra,
        ],
        text=True,
        capture_output=True,
    )


def test_preflight_live_json_passes_without_required_services() -> None:
    with tempfile.TemporaryDirectory() as temp_name:
        root = Path(temp_name)
        now = time.time()
        write_json(
            root / "latest_udp.json",
            {
                "status": "ok",
                "valid": False,
                "fps": 24.0,
                "_received": {"time": now, "from": "127.0.0.1", "port": 5005},
            },
        )
        write_json(
            root / "latest_decision.json",
            {
                "time": now,
                "state": "WAIT_LINKS",
                "reason": "test",
                "command": {},
                "context": {"vision_lock_count": 0, "centered_count": 0, "grab_ready_count": 0},
                "vision": {"ok": False, "age_sec": 0.0, "class": None, "conf": None, "distance_m": None, "dx": None, "dy": None},
                "uwb": {"ok": False, "age_sec": None, "distance_m": None, "azimuth_deg": None, "elevation_deg": None},
                "flight": {"ok": False, "age_sec": None, "armed": None, "system_status": None},
            },
        )
        write_json(root / "latest_arm_action.json", {"time": now, "arm_dry_run": {"mode": "hold", "reason": "test"}})

        proc = run_preflight(root, "--require-live")
        print(proc.stdout)
        assert proc.returncode == 0
        assert "[OK] vision latest" in proc.stdout
        assert "[OK] mission decision" in proc.stdout
        assert "[OK] arm dry-run action" in proc.stdout
        assert "[OK] vision latest schema" in proc.stdout
        assert "[OK] mission decision schema" in proc.stdout
        assert "[OK] arm dry-run action schema" in proc.stdout


def test_preflight_schema_failure_fails() -> None:
    with tempfile.TemporaryDirectory() as temp_name:
        root = Path(temp_name)
        now = time.time()
        write_json(root / "latest_udp.json", {"status": "bad_status", "valid": False, "_received": {"time": now}})
        write_json(
            root / "latest_decision.json",
            {
                "time": now,
                "state": "WAIT_LINKS",
                "reason": "test",
                "command": {},
                "context": {"vision_lock_count": 0, "centered_count": 0, "grab_ready_count": 0},
                "vision": {"ok": False, "age_sec": 0.0, "class": None, "conf": None, "distance_m": None, "dx": None, "dy": None},
                "uwb": {"ok": False, "age_sec": None, "distance_m": None, "azimuth_deg": None, "elevation_deg": None},
                "flight": {"ok": False, "age_sec": None, "armed": None, "system_status": None},
            },
        )
        write_json(root / "latest_arm_action.json", {"time": now, "arm_dry_run": {"mode": "hold", "reason": "test"}})
        proc = run_preflight(root, "--require-live")
        print(proc.stdout)
        assert proc.returncode == 1
        assert "[FAIL] vision latest schema" in proc.stdout


def test_preflight_require_mavlink_fails_without_serial() -> None:
    with tempfile.TemporaryDirectory() as temp_name:
        root = Path(temp_name)
        proc = run_preflight(root, "--require-mavlink")
        print(proc.stdout)
        assert proc.returncode == 1
        assert "[FAIL] MAVLink heartbeat: no serial configured" in proc.stdout


def main() -> int:
    test_preflight_live_json_passes_without_required_services()
    print("OK test_preflight_live_json_passes_without_required_services")
    test_preflight_schema_failure_fails()
    print("OK test_preflight_schema_failure_fails")
    test_preflight_require_mavlink_fails_without_serial()
    print("OK test_preflight_require_mavlink_fails_without_serial")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
