#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mission_state_machine import auto_detect_mavlink_serial


@dataclass
class CheckResult:
    level: str
    name: str
    detail: str


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


def age_from_keys(msg: dict[str, Any], keys: list[str]) -> float | None:
    value: Any = msg
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    try:
        return time.time() - float(value)
    except (TypeError, ValueError):
        return None


def result(level: str, name: str, detail: str) -> CheckResult:
    return CheckResult(level=level, name=name, detail=detail)


def check_service(name: str, required: bool) -> CheckResult:
    if shutil.which("systemctl") is None:
        return result("WARN", name, "systemctl not available on this host")
    proc = subprocess.run(["systemctl", "is-active", name], text=True, capture_output=True)
    state = proc.stdout.strip() or proc.stderr.strip() or f"exit={proc.returncode}"
    if proc.returncode == 0:
        return result("OK", name, "active")
    return result("FAIL" if required else "WARN", name, state)


def check_fresh_json(name: str, path: Path, age: float | None, max_age: float, required: bool) -> CheckResult:
    if age is None:
        exists = path.exists()
        level = "FAIL" if required else "WARN"
        detail = "missing" if not exists else "missing timestamp or invalid JSON"
        return result(level, name, f"{path}: {detail}")
    if age > max_age:
        level = "FAIL" if required else "WARN"
        return result(level, name, f"{path}: stale age_sec={age:.3f} max={max_age}")
    return result("OK", name, f"{path}: age_sec={age:.3f}")


def type_names(value: Any) -> set[str]:
    if value is None:
        return {"null"}
    if isinstance(value, bool):
        return {"boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integer", "number"}
    if isinstance(value, float):
        return {"number"}
    if isinstance(value, str):
        return {"string"}
    if isinstance(value, list):
        return {"array"}
    if isinstance(value, dict):
        return {"object"}
    return {type(value).__name__}


def expected_types(spec: dict[str, Any]) -> set[str]:
    raw = spec.get("type")
    if isinstance(raw, list):
        return set(raw)
    if isinstance(raw, str):
        return {raw}
    return set()


def validate_schema(value: Any, spec: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    types = expected_types(spec)
    if types and type_names(value).isdisjoint(types):
        errors.append(f"{path}: expected {sorted(types)}, got {sorted(type_names(value))}")
        return errors
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: value {value!r} not in enum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            errors.append(f"{path}: {value} < minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            errors.append(f"{path}: {value} > maximum {spec['maximum']}")
    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        for key, child_spec in (spec.get("properties") or {}).items():
            if key in value:
                errors.extend(validate_schema(value[key], child_spec, f"{path}.{key}"))
    if isinstance(value, list) and "items" in spec:
        for idx, item in enumerate(value):
            errors.extend(validate_schema(item, spec["items"], f"{path}[{idx}]"))
    return errors


def check_json_contract(name: str, json_path: Path, schema_path: Path, required: bool) -> CheckResult:
    schema = read_json(schema_path)
    if schema is None:
        return result("WARN", f"{name} schema", f"{schema_path} missing or invalid")
    payload = read_json(json_path)
    if payload is None:
        return result("FAIL" if required else "WARN", f"{name} schema", f"{json_path} missing or invalid JSON")
    errors = validate_schema(payload, schema)
    if errors:
        return result("FAIL", f"{name} schema", "; ".join(errors[:3]))
    return result("OK", f"{name} schema", f"{json_path} matches {schema_path.name}")


def check_vision_latest(path: Path, max_age: float, required: bool) -> CheckResult:
    msg = read_json(path)
    if msg is None:
        return check_fresh_json("vision latest", path, None, max_age, required)
    age = age_from_keys(msg, ["_received", "time"])
    if age is None:
        age = age_from_keys(msg, ["timestamp"])
    base = check_fresh_json("vision latest", path, age, max_age, required)
    if base.level != "OK":
        return base
    status = msg.get("status")
    fps = msg.get("fps")
    target = msg.get("target") or {}
    return result("OK", "vision latest", f"status={status} fps={fps} class={target.get('class')} age_sec={age:.3f}")


def check_decision_latest(path: Path, max_age: float, required: bool) -> CheckResult:
    msg = read_json(path)
    if msg is None:
        return check_fresh_json("mission decision", path, None, max_age, required)
    age = age_from_keys(msg, ["time"])
    base = check_fresh_json("mission decision", path, age, max_age, required)
    if base.level != "OK":
        return base
    return result("OK", "mission decision", f"state={msg.get('state')} reason={msg.get('reason')} age_sec={age:.3f}")


def check_arm_action_latest(path: Path, max_age: float, required: bool) -> CheckResult:
    msg = read_json(path)
    if msg is None:
        return check_fresh_json("arm dry-run action", path, None, max_age, required)
    age = age_from_keys(msg, ["time"])
    base = check_fresh_json("arm dry-run action", path, age, max_age, required)
    if base.level != "OK":
        return base
    action = msg.get("arm_dry_run") or {}
    return result("OK", "arm dry-run action", f"mode={action.get('mode')} reason={action.get('reason')} age_sec={age:.3f}")


def check_uwb_latest(path: Path, max_age: float, required: bool) -> CheckResult:
    msg = read_json(path)
    if msg is None:
        return check_fresh_json("UWB/AOA latest", path, None, max_age, required)
    age = age_from_keys(msg, ["_received_time"])
    if age is None:
        age = age_from_keys(msg, ["timestamp"])
    base = check_fresh_json("UWB/AOA latest", path, age, max_age, required)
    if base.level != "OK":
        return base
    return result(
        "OK",
        "UWB/AOA latest",
        f"cmd={msg.get('cmd')} ok={msg.get('ok')} distance_m={msg.get('distance_m')} azimuth_deg={msg.get('azimuth_deg')} age_sec={age:.3f}",
    )


def check_enable_file(path: Path) -> CheckResult:
    if path.exists():
        return result("WARN", "arm dry-run enable file", f"{path} exists; remove it after bench-only dry-run tests")
    return result("OK", "arm dry-run enable file", f"{path} absent")


def check_jetson_health(url: str | None, required: bool) -> CheckResult:
    if not url:
        return result("WARN", "Jetson health", "no URL configured")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read(500).decode("utf-8", "replace")
    except Exception as exc:
        return result("FAIL" if required else "WARN", "Jetson health", f"{url}: {exc}")
    if '"status":"ok"' in body or '"status": "ok"' in body:
        return result("OK", "Jetson health", url)
    return result("FAIL" if required else "WARN", "Jetson health", f"{url}: unexpected body {body[:120]!r}")


def check_mavlink(args: argparse.Namespace) -> CheckResult:
    serial = args.mavlink_serial or auto_detect_mavlink_serial()
    if not serial:
        return result("FAIL" if args.require_mavlink else "WARN", "MAVLink heartbeat", "no serial configured")
    probe = Path(args.root) / "flight_link_probe.py"
    if not probe.exists():
        probe = Path(__file__).with_name("flight_link_probe.py")
    if not probe.exists():
        return result("FAIL" if args.require_mavlink else "WARN", "MAVLink heartbeat", "flight_link_probe.py not found")
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(probe),
                "--serial",
                serial,
                "--baud",
                str(args.mavlink_baud),
                "--seconds",
                str(args.mavlink_seconds),
            ],
            text=True,
            capture_output=True,
            timeout=args.mavlink_seconds + 3,
        )
        report = json.loads(proc.stdout)
    except Exception as exc:
        return result("FAIL" if args.require_mavlink else "WARN", "MAVLink heartbeat", str(exc))
    mav = report.get("mavlink") or {}
    if not mav.get("ok"):
        return result("FAIL" if args.require_mavlink else "WARN", "MAVLink heartbeat", f"not detected: {mav}")
    if mav.get("armed") is True:
        return result("FAIL", "MAVLink heartbeat", f"flight controller is armed: {mav}")
    return result("OK", "MAVLink heartbeat", f"serial={serial} disarmed heartbeat: {mav}")


def check_arm_servo_config(path: Path) -> CheckResult:
    msg = read_json(path)
    if msg is None:
        return result("WARN", "arm servo config", f"{path} missing or invalid; real servo output should stay disabled")
    if msg.get("enabled") is not False:
        return result("FAIL", "arm servo config", "enabled must remain false until hardware bench validation is complete")
    channels = msg.get("channels") or []
    for channel in channels:
        pulse = channel.get("pulse_us") or {}
        if pulse.get("min") is None or pulse.get("max") is None:
            return result("FAIL", "arm servo config", f"channel {channel.get('name')} missing pulse min/max")
        if not (500 <= pulse["min"] < pulse["max"] <= 2500):
            return result("FAIL", "arm servo config", f"channel {channel.get('name')} pulse range out of expected servo bounds")
    return result("OK", "arm servo config", f"{path}: enabled=false channels={len(channels)}")


def print_results(results: list[CheckResult]) -> int:
    failed = False
    for item in results:
        print(f"[{item.level}] {item.name}: {item.detail}")
        if item.level == "FAIL":
            failed = True
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MP257 preflight checker for the vision/manipulator dry-run stack.")
    parser.add_argument("--root", default="/root/vision_comm")
    parser.add_argument("--vision-latest", default=None)
    parser.add_argument("--decision-latest", default=None)
    parser.add_argument("--arm-action-latest", default=None)
    parser.add_argument("--uwb-latest", default=None)
    parser.add_argument("--arm-enable-file", default=None)
    parser.add_argument("--arm-servo-config", default=None)
    parser.add_argument("--schemas-dir", default=None)
    parser.add_argument("--jetson-health-url", default=os.environ.get("JETSON_HEALTH_URL"))
    parser.add_argument("--mavlink-serial", default=os.environ.get("MAVLINK_SERIAL"))
    parser.add_argument("--mavlink-baud", type=int, default=int(os.environ.get("MAVLINK_BAUD", "115200")))
    parser.add_argument("--mavlink-seconds", type=int, default=int(os.environ.get("MAVLINK_SECONDS", "2")))
    parser.add_argument("--vision-max-age", type=float, default=2.0)
    parser.add_argument("--decision-max-age", type=float, default=2.0)
    parser.add_argument("--arm-action-max-age", type=float, default=2.0)
    parser.add_argument("--uwb-max-age", type=float, default=2.0)
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--require-uwb", action="store_true")
    parser.add_argument("--require-services", action="store_true")
    parser.add_argument("--require-jetson", action="store_true")
    parser.add_argument("--require-mavlink", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    vision_latest = Path(args.vision_latest) if args.vision_latest else root / "latest_udp.json"
    decision_latest = Path(args.decision_latest) if args.decision_latest else root / "latest_decision.json"
    arm_action_latest = Path(args.arm_action_latest) if args.arm_action_latest else root / "latest_arm_action.json"
    uwb_latest = Path(args.uwb_latest) if args.uwb_latest else root / "latest_uwb.json"
    arm_enable_file = Path(args.arm_enable_file) if args.arm_enable_file else root / "ENABLE_ARM_DRY_RUN"
    arm_servo_config = Path(args.arm_servo_config) if args.arm_servo_config else root / "arm_servo_config.json"
    schemas_dir = Path(args.schemas_dir) if args.schemas_dir else root / "schemas"

    results = [
        result("OK" if root.exists() else "WARN", "runtime directory", str(root)),
        check_service("vision-udp-receiver.service", args.require_services),
        check_service("mp257-mission-state-machine.service", args.require_services),
        check_service("mp257-arm-dry-run.service", args.require_services),
        check_jetson_health(args.jetson_health_url, args.require_jetson),
        check_vision_latest(vision_latest, args.vision_max_age, args.require_live),
        check_decision_latest(decision_latest, args.decision_max_age, args.require_live),
        check_arm_action_latest(arm_action_latest, args.arm_action_max_age, args.require_live),
        check_uwb_latest(uwb_latest, args.uwb_max_age, args.require_uwb),
        check_json_contract("vision latest", vision_latest, schemas_dir / "vision_latest.schema.json", args.require_live),
        check_json_contract("mission decision", decision_latest, schemas_dir / "mission_decision.schema.json", args.require_live),
        check_json_contract("arm dry-run action", arm_action_latest, schemas_dir / "arm_action.schema.json", args.require_live),
        check_json_contract("UWB/AOA latest", uwb_latest, schemas_dir / "uwb_aoa.schema.json", args.require_uwb),
        check_enable_file(arm_enable_file),
        check_arm_servo_config(arm_servo_config),
        check_mavlink(args),
    ]
    return print_results(results)


if __name__ == "__main__":
    raise SystemExit(main())
