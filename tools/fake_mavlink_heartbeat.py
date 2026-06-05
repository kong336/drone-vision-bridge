#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import struct
import time


def heartbeat_frame(seq: int, armed: bool, system_status: int) -> bytes:
    # MAVLink v1 HEARTBEAT. The monitor intentionally ignores CRC because it is read-only.
    payload = struct.pack(
        "<IBBBBB",
        0,      # custom_mode
        2,      # MAV_TYPE_QUADROTOR
        3,      # MAV_AUTOPILOT_ARDUPILOTMEGA
        0x80 if armed else 0,
        system_status,
        3,      # mavlink_version
    )
    header = bytes([0xFE, len(payload), seq & 0xFF, 1, 1, 0])
    return header + payload + b"\x00\x00"


def main() -> int:
    parser = argparse.ArgumentParser(description="Send fake MAVLink HEARTBEAT packets for local bench tests.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=14550)
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--system-status", type=int, default=3)
    args = parser.parse_args()

    interval = 1.0 / args.rate if args.rate > 0 else 0.2
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    deadline = time.time() + args.seconds
    seq = 0
    try:
        while time.time() < deadline:
            frame = heartbeat_frame(seq, args.armed, args.system_status)
            sock.sendto(frame, (args.host, args.port))
            print(f"sent heartbeat seq={seq} armed={args.armed} to {args.host}:{args.port}", flush=True)
            seq += 1
            time.sleep(interval)
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
