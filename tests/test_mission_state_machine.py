from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mp257"))

import mission_state_machine as msm


def default_args() -> argparse.Namespace:
    return argparse.Namespace(
        require_flight=True,
        target_class="wrench",
        min_conf=0.35,
        align_px=40,
        lock_frames=3,
        center_frames=5,
        grab_frames=8,
        uwb_near_m=2.0,
        grab_distance_m=0.45,
        max_velocity_mps=0.35,
        max_vertical_mps=0.2,
        max_yaw_rate=12.0,
        vision_max_age=2.0,
        uwb_max_age=2.0,
        replay_temp="/tmp/replay.json",
    )


def run_replay(path: Path) -> list[dict]:
    args = default_args()
    context = msm.DecisionContext()
    state = msm.MissionState.BOOT
    reports = []
    for item in msm.load_replay(path):
        vision, uwb, flight = msm.replay_state(item, args)
        context.update(vision, args)
        decision = msm.choose_state(state, vision, uwb, flight, args, context)
        state = decision.state
        reports.append(msm.build_report(state, decision, vision, uwb, flight, context))
    return reports


def choose_sequence(items: list[dict]) -> list[dict]:
    args = default_args()
    context = msm.DecisionContext()
    state = msm.MissionState.BOOT
    reports = []
    for item in items:
        vision, uwb, flight = msm.replay_state(item, args)
        context.update(vision, args)
        decision = msm.choose_state(state, vision, uwb, flight, args, context)
        state = decision.state
        reports.append(msm.build_report(state, decision, vision, uwb, flight, context))
    return reports


def live_uwb_file_report() -> dict:
    args = default_args()
    state = msm.MissionState.BOOT
    context = msm.DecisionContext()
    with tempfile.TemporaryDirectory() as temp_name:
        uwb_path = Path(temp_name) / "latest_uwb.json"
        uwb_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "cmd": "location",
                    "distance_m": 3.2,
                    "azimuth_deg": 30,
                    "elevation_deg": 4,
                    "_received_time": time.time(),
                }
            ),
            encoding="utf-8",
        )
        vision = msm.VisionState(ok=False)
        uwb = msm.read_uwb(uwb_path, args.uwb_max_age)
        flight = msm.FlightState(ok=True, armed=False, system_status=3)
        context.update(vision, args)
        decision = msm.choose_state(state, vision, uwb, flight, args, context)
        return msm.build_report(decision.state, decision, vision, uwb, flight, context)


def main() -> int:
    reports = run_replay(ROOT / "tests" / "mission_replay_scenarios.jsonl")
    states = [r["state"] for r in reports]
    close_off_center = choose_sequence(
        [
            {
                "vision": {
                    "status": "ok",
                    "valid": True,
                    "target": {"class": "wrench", "conf": 0.95, "distance_m": 0.35, "offset": {"dx": 180, "dy": 0}},
                    "detections": [{}],
                },
                "flight": {"ok": True, "armed": False, "system_status": 3},
            }
            for _ in range(8)
        ]
    )
    live_uwb = live_uwb_file_report()

    checks = {
        "single_frame_does_not_lock": states[1] == "IDLE_SAFE",
        "lost_resets_lock_counter": reports[2]["context"]["vision_lock_count"] == 0,
        "uwb_far_approach": states[3] == "UWB_APPROACH",
        "third_stable_lock": states[6] == "VISION_LOCK",
        "fifth_centered_fine_align": states[11] == "FINE_ALIGN",
        "eighth_grab_frame_dry_run": states[19] == "GRAB_DRY_RUN",
        "armed_forces_failsafe": states[20] == "FAILSAFE",
        "close_off_center_stays_vision_lock": close_off_center[-1]["state"] == "VISION_LOCK",
        "live_uwb_latest_drives_approach": live_uwb["state"] == "UWB_APPROACH",
    }
    print(json.dumps({"states": states, "checks": checks}, indent=2))
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
