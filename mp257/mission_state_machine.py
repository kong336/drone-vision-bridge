#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import select
import socket
import struct
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import termios
except ImportError:
    termios = None


def auto_detect_mavlink_serial() -> str | None:
    for pattern in ("/dev/serial/by-id/*ArduPilot*", "/dev/serial/by-id/*PX4*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


class MissionState(str, Enum):
    BOOT = "BOOT"
    WAIT_LINKS = "WAIT_LINKS"
    WAIT_FLIGHT_SAFE = "WAIT_FLIGHT_SAFE"
    IDLE_SAFE = "IDLE_SAFE"
    UWB_SEARCH = "UWB_SEARCH"
    UWB_APPROACH = "UWB_APPROACH"
    VISION_LOCK = "VISION_LOCK"
    FINE_ALIGN = "FINE_ALIGN"
    GRAB_READY = "GRAB_READY"
    GRAB_DRY_RUN = "GRAB_DRY_RUN"
    HOLD = "HOLD"
    FAILSAFE = "FAILSAFE"


@dataclass
class VisionState:
    ok: bool = False
    age_sec: float | None = None
    target_class: str | None = None
    conf: float | None = None
    distance_m: float | None = None
    dx: int | None = None
    dy: int | None = None
    fps: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UwbState:
    ok: bool = False
    age_sec: float | None = None
    distance_m: float | None = None
    azimuth_deg: float | None = None
    elevation_deg: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlightState:
    ok: bool = False
    age_sec: float | None = None
    system_id: int | None = None
    component_id: int | None = None
    base_mode: int | None = None
    system_status: int | None = None
    armed: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    state: MissionState
    reason: str
    command: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionContext:
    vision_lock_count: int = 0
    centered_count: int = 0
    grab_ready_count: int = 0

    def update(self, vision: VisionState, args: argparse.Namespace) -> None:
        locked = vision_target_locked(vision, args)
        centered = locked and vision.dx is not None and abs(vision.dx) <= args.align_px
        grab_ready = centered and vision.distance_m is not None and vision.distance_m <= args.grab_distance_m

        self.vision_lock_count = self.vision_lock_count + 1 if locked else 0
        self.centered_count = self.centered_count + 1 if centered else 0
        self.grab_ready_count = self.grab_ready_count + 1 if grab_ready else 0


class MavlinkMonitor:
    """Minimal MAVLink heartbeat monitor.

    This only decodes HEARTBEAT frames. It does not send commands.
    """

    def __init__(self, serial_path: str | None = None, baud: int = 57600, udp_port: int | None = None):
        self.serial_path = serial_path
        self.serial_auto = serial_path == "auto"
        self.baud = baud
        self.udp_port = udp_port
        self.fd: int | None = None
        self.sock: socket.socket | None = None
        self.buffer = bytearray()
        self.latest: FlightState = FlightState()
        self.last_auto_detect_time = 0.0

    def open(self) -> None:
        if self.serial_auto:
            self._open_auto_serial()
        elif self.serial_path:
            self._open_serial(self.serial_path)
        if self.udp_port:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            self.sock.bind(("0.0.0.0", self.udp_port))

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def poll(self) -> FlightState:
        if self.serial_auto and self.fd is None:
            self._open_auto_serial()
        if self.fd is not None:
            ready, _, _ = select.select([self.fd], [], [], 0)
            if ready:
                self.buffer.extend(os.read(self.fd, 512))
        if self.sock is not None:
            while True:
                try:
                    data, _ = self.sock.recvfrom(2048)
                except BlockingIOError:
                    break
                self.buffer.extend(data)

        for msg in self._consume_messages():
            if msg["msgid"] == 0:
                self.latest = self._decode_heartbeat(msg)

        if self.latest.raw:
            self.latest.age_sec = time.time() - self.latest.raw.get("_received_time", 0)
            self.latest.ok = self.latest.age_sec <= 3.0
        return self.latest

    def _open_auto_serial(self) -> bool:
        now = time.time()
        if now - self.last_auto_detect_time < 2.0:
            return False
        self.last_auto_detect_time = now
        detected = auto_detect_mavlink_serial()
        if detected is None:
            self.serial_path = None
            return False
        self.serial_path = detected
        self._open_serial(detected)
        return True

    def _open_serial(self, path: str) -> None:
        if termios is None:
            raise SystemExit("serial MAVLink mode requires Linux termios; use --mavlink-udp-port or --replay on this host")
        self.fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure_serial(self.fd, self.baud)

    def _configure_serial(self, fd: int, baud: int) -> None:
        if termios is None:
            raise SystemExit("serial MAVLink mode requires Linux termios")
        baud_map = {
            57600: termios.B57600,
            115200: termios.B115200,
            230400: termios.B230400,
            460800: getattr(termios, "B460800", termios.B230400),
            921600: getattr(termios, "B921600", termios.B230400),
        }
        speed = baud_map.get(baud)
        if speed is None:
            raise SystemExit(f"unsupported MAVLink baud: {baud}")

        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = speed
        attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1
        termios.tcsetattr(fd, termios.TCSANOW, attrs)

    def _consume_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        while self.buffer:
            magic_index = next((i for i, b in enumerate(self.buffer) if b in (0xFE, 0xFD)), -1)
            if magic_index < 0:
                self.buffer.clear()
                break
            if magic_index:
                del self.buffer[:magic_index]
            if len(self.buffer) < 8:
                break

            magic = self.buffer[0]
            payload_len = self.buffer[1]
            if magic == 0xFE:
                frame_len = 6 + payload_len + 2
                if len(self.buffer) < frame_len:
                    break
                sysid = self.buffer[3]
                compid = self.buffer[4]
                msgid = self.buffer[5]
                payload = bytes(self.buffer[6 : 6 + payload_len])
                del self.buffer[:frame_len]
                messages.append({"msgid": msgid, "sysid": sysid, "compid": compid, "payload": payload})
            else:
                incompat_flags = self.buffer[2]
                signature_len = 13 if incompat_flags & 0x01 else 0
                frame_len = 10 + payload_len + 2 + signature_len
                if len(self.buffer) < frame_len:
                    break
                sysid = self.buffer[5]
                compid = self.buffer[6]
                msgid = int.from_bytes(self.buffer[7:10], "little")
                payload = bytes(self.buffer[10 : 10 + payload_len])
                del self.buffer[:frame_len]
                messages.append({"msgid": msgid, "sysid": sysid, "compid": compid, "payload": payload})
        return messages

    def _decode_heartbeat(self, msg: dict[str, Any]) -> FlightState:
        payload = msg["payload"]
        if len(payload) < 9:
            return self.latest
        custom_mode, mav_type, autopilot, base_mode, system_status, mavlink_version = struct.unpack_from("<IBBBBB", payload)
        armed = bool(base_mode & 0x80)
        raw = {
            "_received_time": time.time(),
            "custom_mode": custom_mode,
            "type": mav_type,
            "autopilot": autopilot,
            "mavlink_version": mavlink_version,
        }
        return FlightState(
            ok=True,
            age_sec=0.0,
            system_id=msg["sysid"],
            component_id=msg["compid"],
            base_mode=base_mode,
            system_status=system_status,
            armed=armed,
            raw=raw,
        )


def read_json_file(path: Path) -> dict[str, Any] | None:
    for attempt in range(5):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        except PermissionError:
            if attempt == 4:
                return None
            time.sleep(0.05)
    return None


def read_vision(path: Path, max_age: float) -> VisionState:
    msg = read_json_file(path)
    if not msg:
        return VisionState(ok=False)
    return parse_vision_message(msg, max_age)


def parse_vision_message(msg: dict[str, Any], max_age: float) -> VisionState:
    received = (msg.get("_received") or {}).get("time", msg.get("timestamp"))
    age = time.time() - float(received) if received else None
    target = msg.get("target_smoothed") or msg.get("target") or {}
    offset = target.get("offset") or {}
    distance = target.get("distance_m", msg.get("distance_m"))
    ok = msg.get("status") == "ok" and age is not None and age <= max_age
    return VisionState(
        ok=ok,
        age_sec=age,
        target_class=target.get("class"),
        conf=target.get("conf"),
        distance_m=float(distance) if distance is not None else None,
        dx=offset.get("dx"),
        dy=offset.get("dy"),
        fps=msg.get("fps"),
        raw=msg,
    )


def vision_target_locked(vision: VisionState, args: argparse.Namespace) -> bool:
    return bool(
        vision.ok
        and vision.target_class
        and vision.conf is not None
        and vision.conf >= args.min_conf
        and (not args.target_class or vision.target_class == args.target_class)
    )


def read_uwb(path: Path | None, max_age: float) -> UwbState:
    if path is None:
        return UwbState(ok=False)
    msg = read_json_file(path)
    if not msg:
        return UwbState(ok=False)
    received = msg.get("_received_time", msg.get("timestamp", time.time()))
    age = time.time() - float(received)
    ok = bool(msg.get("ok")) and age <= max_age
    return UwbState(
        ok=ok,
        age_sec=age,
        distance_m=msg.get("distance_m"),
        azimuth_deg=msg.get("azimuth_deg"),
        elevation_deg=msg.get("elevation_deg"),
        raw=msg,
    )


def choose_state(
    current: MissionState,
    vision: VisionState,
    uwb: UwbState,
    flight: FlightState,
    args: argparse.Namespace,
    context: DecisionContext | None = None,
) -> Decision:
    if context is None:
        context = DecisionContext()
        context.update(vision, args)

    if args.require_flight and not flight.ok:
        return Decision(MissionState.WAIT_FLIGHT_SAFE, "waiting for MAVLink heartbeat")

    if args.require_flight and flight.armed:
        return Decision(MissionState.FAILSAFE, "flight controller is already armed; monitor-only state machine refuses to take over")

    if not vision.ok and not uwb.ok:
        return Decision(MissionState.WAIT_LINKS, "waiting for vision or UWB/AOA data")

    if vision_target_locked(vision, args):
        if context.vision_lock_count < args.lock_frames:
            return Decision(
                MissionState.IDLE_SAFE,
                f"vision target candidate seen {context.vision_lock_count}/{args.lock_frames} frames",
            )
        if vision.dx is not None and abs(vision.dx) <= args.align_px:
            if context.centered_count < args.center_frames:
                return Decision(
                    MissionState.VISION_LOCK,
                    f"vision target near center {context.centered_count}/{args.center_frames} frames",
                    velocity_command(vision, args),
                )
            if vision.distance_m is not None and vision.distance_m <= args.grab_distance_m:
                if context.grab_ready_count < args.grab_frames:
                    return Decision(
                        MissionState.GRAB_READY,
                        f"target centered and in grab range but waiting for stable confirmation {context.grab_ready_count}/{args.grab_frames}",
                        velocity_command(vision, args),
                    )
                return Decision(MissionState.GRAB_DRY_RUN, "target is stably centered within dry-run grab distance", {"arm": "would_grab"})
            return Decision(MissionState.FINE_ALIGN, "vision target stably centered for slow approach", velocity_command(vision, args))
        return Decision(MissionState.VISION_LOCK, "vision target acquired; align to image center", velocity_command(vision, args))

    if uwb.ok and uwb.distance_m is not None and uwb.azimuth_deg is not None:
        if uwb.distance_m > args.uwb_near_m:
            return Decision(MissionState.UWB_APPROACH, "UWB target is far; coarse approach", uwb_command(uwb, args))
        return Decision(MissionState.UWB_SEARCH, "UWB target near; wait for vision lock", uwb_command(uwb, args))

    return Decision(MissionState.IDLE_SAFE, "links present but no actionable target")


def velocity_command(vision: VisionState, args: argparse.Namespace) -> dict[str, Any]:
    dx = float(vision.dx or 0)
    dy = float(vision.dy or 0)
    distance = vision.distance_m
    yaw_rate = max(-args.max_yaw_rate, min(args.max_yaw_rate, dx / args.align_px * args.max_yaw_rate))
    vz = max(-args.max_vertical_mps, min(args.max_vertical_mps, dy / args.align_px * args.max_vertical_mps))
    vx = 0.0
    if distance is not None:
        vx = max(-args.max_velocity_mps, min(args.max_velocity_mps, (distance - args.grab_distance_m) * 0.25))
    return {"mode": "dry_run_velocity", "vx_mps": round(vx, 3), "vz_mps": round(vz, 3), "yaw_rate_dps": round(yaw_rate, 3)}


def uwb_command(uwb: UwbState, args: argparse.Namespace) -> dict[str, Any]:
    az = math.radians(float(uwb.azimuth_deg or 0))
    distance = float(uwb.distance_m or 0)
    speed = min(args.max_velocity_mps, max(0.0, (distance - args.uwb_near_m) * 0.2))
    return {
        "mode": "dry_run_coarse_velocity",
        "vx_mps": round(speed * math.cos(az), 3),
        "vy_mps": round(speed * math.sin(az), 3),
        "yaw_to_azimuth_deg": round(float(uwb.azimuth_deg or 0), 2),
    }


def load_replay(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_latest(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    replace_with_retry(tmp, path)


def replace_with_retry(tmp: Path, path: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def replay_state(item: dict[str, Any], args: argparse.Namespace) -> tuple[VisionState, UwbState, FlightState]:
    now = time.time()
    vision_msg = item.get("vision")
    if vision_msg is None and ("target" in item or "status" in item):
        vision_msg = item
    if vision_msg is not None:
        if "timestamp" not in vision_msg and "_received" not in vision_msg:
            vision_msg = dict(vision_msg)
            vision_msg["_received"] = {"time": now}
        vision = parse_vision_message(vision_msg, args.vision_max_age)
    else:
        vision = VisionState(ok=False)

    uwb_msg = item.get("uwb")
    if uwb_msg:
        uwb = UwbState(
            ok=bool(uwb_msg.get("ok", True)),
            age_sec=0.0,
            distance_m=uwb_msg.get("distance_m"),
            azimuth_deg=uwb_msg.get("azimuth_deg"),
            elevation_deg=uwb_msg.get("elevation_deg"),
            raw=uwb_msg,
        )
    else:
        uwb = UwbState(ok=False)

    flight_msg = item.get("flight") or {}
    flight = FlightState(
        ok=bool(flight_msg.get("ok", False)),
        age_sec=0.0 if flight_msg else None,
        system_id=flight_msg.get("system_id"),
        component_id=flight_msg.get("component_id"),
        base_mode=flight_msg.get("base_mode"),
        system_status=flight_msg.get("system_status"),
        armed=flight_msg.get("armed"),
        raw=flight_msg,
    )
    return vision, uwb, flight


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor-only mission state machine for Jetson + MP257 + UWB/AOA.")
    parser.add_argument("--vision-latest", default="/root/vision_comm/latest_udp.json")
    parser.add_argument("--uwb-latest", default=None)
    parser.add_argument("--mavlink-serial", default=None, help="Serial device, or 'auto' to use /dev/serial/by-id/*ArduPilot* or *PX4*.")
    parser.add_argument("--mavlink-baud", type=int, default=57600)
    parser.add_argument("--mavlink-udp-port", type=int, default=None)
    parser.add_argument("--require-flight", action="store_true")
    parser.add_argument("--target-class", default="wrench")
    parser.add_argument("--min-conf", type=float, default=0.35)
    parser.add_argument("--align-px", type=int, default=40)
    parser.add_argument("--lock-frames", type=int, default=3)
    parser.add_argument("--center-frames", type=int, default=5)
    parser.add_argument("--grab-frames", type=int, default=8)
    parser.add_argument("--uwb-near-m", type=float, default=2.0)
    parser.add_argument("--grab-distance-m", type=float, default=0.45)
    parser.add_argument("--max-velocity-mps", type=float, default=0.35)
    parser.add_argument("--max-vertical-mps", type=float, default=0.2)
    parser.add_argument("--max-yaw-rate", type=float, default=12.0)
    parser.add_argument("--vision-max-age", type=float, default=2.0)
    parser.add_argument("--uwb-max-age", type=float, default=2.0)
    parser.add_argument("--period", type=float, default=0.2)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--decision-latest", default=None, help="Write the latest state-machine decision JSON to this path.")
    parser.add_argument("--replay", default=None, help="Replay JSON/JSONL samples instead of reading live files.")
    parser.add_argument("--replay-temp", default=str(Path(tempfile.gettempdir()) / "mission_state_machine_replay_latest.json"))
    args = parser.parse_args()

    context = DecisionContext()
    if args.replay:
        state = MissionState.BOOT
        for item in load_replay(Path(args.replay)):
            vision, uwb, flight = replay_state(item, args)
            context.update(vision, args)
            decision = choose_state(state, vision, uwb, flight, args, context)
            state = decision.state
            report = build_report(state, decision, vision, uwb, flight, context)
            write_latest(Path(args.decision_latest) if args.decision_latest else None, report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0

    mav = MavlinkMonitor(args.mavlink_serial, args.mavlink_baud, args.mavlink_udp_port)
    mav.open()
    state = MissionState.BOOT
    try:
        while True:
            vision = read_vision(Path(args.vision_latest), args.vision_max_age)
            uwb = read_uwb(Path(args.uwb_latest) if args.uwb_latest else None, args.uwb_max_age)
            flight = mav.poll()
            context.update(vision, args)
            decision = choose_state(state, vision, uwb, flight, args, context)
            state = decision.state
            report = build_report(state, decision, vision, uwb, flight, context)
            write_latest(Path(args.decision_latest) if args.decision_latest else None, report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if args.once:
                break
            time.sleep(args.period)
    finally:
        mav.close()
    return 0


def build_report(
    state: MissionState,
    decision: Decision,
    vision: VisionState,
    uwb: UwbState,
    flight: FlightState,
    context: DecisionContext,
) -> dict[str, Any]:
    return {
        "time": round(time.time(), 3),
        "state": state.value,
        "reason": decision.reason,
        "command": decision.command,
        "context": {
            "vision_lock_count": context.vision_lock_count,
            "centered_count": context.centered_count,
            "grab_ready_count": context.grab_ready_count,
        },
        "vision": {
            "ok": vision.ok,
            "age_sec": round(vision.age_sec, 3) if vision.age_sec is not None else None,
            "class": vision.target_class,
            "conf": vision.conf,
            "distance_m": vision.distance_m,
            "dx": vision.dx,
            "dy": vision.dy,
        },
        "uwb": {
            "ok": uwb.ok,
            "age_sec": round(uwb.age_sec, 3) if uwb.age_sec is not None else None,
            "distance_m": uwb.distance_m,
            "azimuth_deg": uwb.azimuth_deg,
            "elevation_deg": uwb.elevation_deg,
        },
        "flight": {
            "ok": flight.ok,
            "age_sec": round(flight.age_sec, 3) if flight.age_sec is not None else None,
            "armed": flight.armed,
            "system_status": flight.system_status,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
