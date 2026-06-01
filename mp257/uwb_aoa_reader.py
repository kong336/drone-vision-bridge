#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from dataclasses import dataclass


HEADER = b"\xff\xff\xff\xff"
CMD_LOCATION = 0x2001
CMD_HEARTBEAT = 0x2002


@dataclass
class ParseResult:
    consumed: int
    message: dict | None


def xor8(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
    return value


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big", signed=False)


def s16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big", signed=True)


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big", signed=False)


def parse_one(buffer: bytes) -> ParseResult:
    start = buffer.find(HEADER)
    if start < 0:
        return ParseResult(max(0, len(buffer) - 3), None)
    if start:
        return ParseResult(start, None)
    if len(buffer) < 6:
        return ParseResult(0, None)

    frame_len = u16(buffer, 4)
    if frame_len < 12 or frame_len > 100:
        return ParseResult(1, {"ok": False, "error": "bad_length", "frame_len": frame_len})
    if len(buffer) < frame_len:
        return ParseResult(0, None)

    frame = buffer[:frame_len]
    cmd = u16(frame, 8)
    version = u16(frame, 10)

    if cmd == CMD_LOCATION:
        if frame_len < 37:
            return ParseResult(frame_len, {"ok": False, "error": "short_location_frame", "frame_len": frame_len})
        check_ok = xor8(frame[:-1]) == frame[-1]
        distance_cm = u32(frame, 20)
        msg = {
            "ok": check_ok,
            "cmd": "location",
            "version": version,
            "sequence_id": u16(frame, 6),
            "anchor_id": u32(frame, 12),
            "tag_id": u32(frame, 16),
            "distance_cm": distance_cm,
            "distance_m": distance_cm / 100.0,
            "azimuth_deg": s16(frame, 24),
            "elevation_deg": s16(frame, 26),
            "tag_status": u16(frame, 28),
            "batch_sn": u16(frame, 30),
            "checksum": frame[-1],
        }
        return ParseResult(frame_len, msg)

    if cmd == CMD_HEARTBEAT:
        msg = {
            "ok": True,
            "cmd": "heartbeat",
            "version": version,
            "sequence_id": u16(frame, 6),
            "anchor_id": u32(frame, 12) if frame_len >= 16 else None,
        }
        return ParseResult(frame_len, msg)

    return ParseResult(frame_len, {"ok": False, "error": "unknown_cmd", "cmd": cmd, "frame_len": frame_len})


def parse_stream_bytes(data: bytes) -> list[dict]:
    messages: list[dict] = []
    buffer = data
    while buffer:
        result = parse_one(buffer)
        if result.consumed == 0:
            break
        if result.message is not None:
            messages.append(result.message)
        buffer = buffer[result.consumed :]
    return messages


def configure_serial(fd: int, baud: int) -> None:
    if os.name == "nt":
        raise SystemExit("serial mode is intended for Linux on the STM32MP257; use --hex on Windows")

    import termios

    baud_map = {
        9600: termios.B9600,
        19200: termios.B19200,
        38400: termios.B38400,
        57600: termios.B57600,
        115200: termios.B115200,
        230400: termios.B230400,
    }
    speed = baud_map.get(baud)
    if speed is None:
        raise SystemExit(f"unsupported baud rate: {baud}")

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


def read_serial(path: str, baud: int) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_serial(fd, baud)
        buffer = b""
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if not ready:
                continue
            chunk = os.read(fd, 256)
            if not chunk:
                time.sleep(0.05)
                continue
            buffer += chunk
            while True:
                result = parse_one(buffer)
                if result.consumed == 0:
                    break
                if result.message is not None:
                    print(json.dumps(result.message, ensure_ascii=False), flush=True)
                buffer = buffer[result.consumed :]
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read ALX-AOA-FIT UWB AOA UART frames.")
    parser.add_argument("--hex", help="Parse one or more hex frames, for example: 'FF FF FF FF ...'")
    parser.add_argument("--serial", help="Linux serial device, for example /dev/ttySTM1 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    if args.hex:
        data = bytes.fromhex(args.hex)
        for msg in parse_stream_bytes(data):
            print(json.dumps(msg, ensure_ascii=False))
        return 0

    if args.serial:
        read_serial(args.serial, args.baud)
        return 0

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
