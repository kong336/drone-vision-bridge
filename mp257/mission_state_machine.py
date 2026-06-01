#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import select
import socket
import struct
import sys
import termios
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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


class MavlinkMonitor:
    """Minimal MAVLink heartbeat monitor.

    This only decodes HEARTBEAT frames. It does not send commands.
    """

    def __init__(self, serial_path: str | None = None, baud: int = 57600, udp_port: int | None = None):
        self.serial_path = serial_path
        self.baud = baud
        self.udp_port = udp_port
        self.fd: int | None = None
        self.sock: socket.socket | None = None
        self.buffer = bytearray()
        self.latest: FlightState = FlightState()

    def open(self) -> None:
        if self.serial_path:
            self.fd = os.open(self.serial_path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
            self._configure_serial(self.fd, self.baud)
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

    def _configure_serial(self, fd: int, baud: int) -> None:
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
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def read_vision(path: Path, max_age: float) -> VisionState:
    msg = read_json_file(path)
    if not msg:
        return VisionState(ok=False)
    received = (msg.get("_received") or {}).get("time", msg.get("timestamp"))
    age = time.time() - float(received) if received else None
    target = msg.get("target") or {}
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


def choose_state(current: MissionState, vision: VisionState, uwb: UwbState, flight: FlightState, args: argparse.Namespace) -> Decision:
    if args.require_flight and not flight.ok:
        return Decision(MissionState.WAIT_FLIGHT_SAFE, "waiting for MAVLink heartbeat")

    if args.require_flight and flight.armed:
        return Decision(MissionState.FAILSAFE, "flight controller is already armed; monitor-only state machine refuses to take over")

    if not vision.ok and not uwb.ok:
        return Decision(MissionState.WAIT_LINKS, "waiting for vision or UWB/AOA data")

    if vision.ok and vision.target_class and vision.conf is not None and vision.conf >= args.min_conf:
        if vision.distance_m is not None and vision.distance_m <= args.grab_distance_m:
            return Decision(MissionState.GRAB_DRY_RUN, "target is within dry-run grab distance", {"arm": "would_grab"})
        if vision.dx is not None and abs(vision.dx) <= args.align_px:
            return Decision(MissionState.FINE_ALIGN, "vision target centered enough for slow approach", velocity_command(vision, args))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor-only mission state machine for Jetson + MP257 + UWB/AOA.")
    parser.add_argument("--vision-latest", default="/root/vision_comm/latest_udp.json")
    parser.add_argument("--uwb-latest", default=None)
    parser.add_argument("--mavlink-serial", default=None)
    parser.add_argument("--mavlink-baud", type=int, default=57600)
    parser.add_argument("--mavlink-udp-port", type=int, default=None)
    parser.add_argument("--require-flight", action="store_true")
    parser.add_argument("--min-conf", type=float, default=0.35)
    parser.add_argument("--align-px", type=int, default=40)
    parser.add_argument("--uwb-near-m", type=float, default=2.0)
    parser.add_argument("--grab-distance-m", type=float, default=0.45)
    parser.add_argument("--max-velocity-mps", type=float, default=0.35)
    parser.add_argument("--max-vertical-mps", type=float, default=0.2)
    parser.add_argument("--max-yaw-rate", type=float, default=12.0)
    parser.add_argument("--vision-max-age", type=float, default=2.0)
    parser.add_argument("--uwb-max-age", type=float, default=2.0)
    parser.add_argument("--period", type=float, default=0.2)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    mav = MavlinkMonitor(args.mavlink_serial, args.mavlink_baud, args.mavlink_udp_port)
    mav.open()
    state = MissionState.BOOT
    try:
        while True:
            vision = read_vision(Path(args.vision_latest), args.vision_max_age)
            uwb = read_uwb(Path(args.uwb_latest) if args.uwb_latest else None, args.uwb_max_age)
            flight = mav.poll()
            decision = choose_state(state, vision, uwb, flight, args)
            state = decision.state
            print(json.dumps({
                "time": round(time.time(), 3),
                "state": state.value,
                "reason": decision.reason,
                "command": decision.command,
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
                    "distance_m": uwb.distance_m,
                    "azimuth_deg": uwb.azimuth_deg,
                },
                "flight": {
                    "ok": flight.ok,
                    "age_sec": round(flight.age_sec, 3) if flight.age_sec is not None else None,
                    "armed": flight.armed,
                    "system_status": flight.system_status,
                },
            }, ensure_ascii=False), flush=True)
            if args.once:
                break
            time.sleep(args.period)
    finally:
        mav.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
