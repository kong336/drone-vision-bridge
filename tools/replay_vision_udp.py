#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path


def load_samples(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def extract_vision(sample: dict) -> dict:
    msg = sample.get("vision")
    if msg is None:
        msg = {k: v for k, v in sample.items() if k not in {"name", "flight", "uwb"}}
    msg = dict(msg)
    msg.setdefault("status", "ok")
    msg.setdefault("timestamp", time.time())
    msg.setdefault("image", {"w": 640, "h": 480, "center_x": 320, "center_y": 240})
    msg.setdefault("detections", [] if not msg.get("target") else [msg["target"]])
    msg.setdefault("valid", bool(msg.get("target")))
    return msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Jetson vision JSON samples over UDP.")
    parser.add_argument("--samples", default="tests/mission_replay_scenarios.jsonl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    samples = load_samples(Path(args.samples))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        while True:
            for sample in samples:
                msg = extract_vision(sample)
                msg["timestamp"] = time.time()
                payload = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                sock.sendto(payload, (args.host, args.port))
                print(f"sent {sample.get('name', '?')} {len(payload)} bytes to {args.host}:{args.port}", flush=True)
                time.sleep(args.interval)
            if not args.loop:
                break
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
