#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from mission_state_machine import MavlinkMonitor


def trim_text(text: str, tail_lines: int | None = None, contains: list[str] | None = None) -> str:
    lines = text.strip().splitlines()
    if contains:
        needles = [item.lower() for item in contains]
        lines = [line for line in lines if any(needle in line.lower() for needle in needles)]
    if tail_lines is not None:
        lines = lines[-tail_lines:]
    return "\n".join(lines)


def run_cmd(args: list[str], tail_lines: int | None = None, contains: list[str] | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, text=True, capture_output=True, timeout=3)
        stdout = trim_text(proc.stdout, tail_lines=tail_lines, contains=contains)
        stderr = trim_text(proc.stderr, tail_lines=tail_lines, contains=contains)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"{args[0]} not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}


def serial_devices() -> list[dict[str, Any]]:
    paths = sorted(set(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyAMA*") + glob.glob("/dev/ttySTM*")))
    rows: list[dict[str, Any]] = []
    for path in paths:
        st = os.stat(path)
        row: dict[str, Any] = {
            "path": path,
            "mode": oct(st.st_mode & 0o777),
            "by_id": [],
            "notes": [],
        }
        for link in sorted(glob.glob("/dev/serial/by-id/*")):
            try:
                if Path(link).resolve() == Path(path).resolve():
                    row["by_id"].append(link)
            except FileNotFoundError:
                pass
        name = Path(path).name
        getty = run_cmd(["systemctl", "is-active", f"serial-getty@{name}.service"])
        if getty.get("stdout") == "active":
            row["notes"].append("serial-getty-active; likely console, do not use for flight control unless intentionally rewired")
        rows.append(row)
    return rows


def poll_mavlink(args: argparse.Namespace) -> dict[str, Any]:
    if not args.serial and args.udp_port is None:
        return {"checked": False, "reason": "no --serial or --udp-port provided"}
    mon = MavlinkMonitor(serial_path=args.serial, baud=args.baud, udp_port=args.udp_port)
    started = time.time()
    try:
        mon.open()
        latest = None
        while time.time() - started < args.seconds:
            latest = mon.poll()
            if latest.ok:
                break
            time.sleep(0.05)
        if latest is None:
            latest = mon.latest
        return {
            "checked": True,
            "ok": latest.ok,
            "age_sec": round(latest.age_sec, 3) if latest.age_sec is not None else None,
            "system_id": latest.system_id,
            "component_id": latest.component_id,
            "armed": latest.armed,
            "system_status": latest.system_status,
            "raw": latest.raw,
        }
    finally:
        mon.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MP257 flight-link probe. It never sends MAVLink commands.")
    parser.add_argument("--serial", default=None, help="Serial device to monitor, for example /dev/ttyACM0.")
    parser.add_argument("--baud", type=int, default=57600)
    parser.add_argument("--udp-port", type=int, default=None, help="UDP port to listen on for MAVLink heartbeat.")
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()

    report = {
        "time": round(time.time(), 3),
        "serial_devices": serial_devices(),
        "usb": run_cmd(["lsusb"]),
        "kernel_tty_tail": run_cmd(
            ["dmesg", "--ctime", "--level=err,warn,info"],
            tail_lines=40,
            contains=["tty", "usb", "acm", "serial", "cdc"],
        ),
        "mavlink": poll_mavlink(args),
        "safety": "probe-only; no arm, takeoff, mode, or movement command is sent",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
