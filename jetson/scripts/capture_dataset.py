#!/usr/bin/env python3
import argparse
import time
from pathlib import Path

import cv2


def parse_source(value):
    return int(value) if value.isdigit() else value


def main():
    parser = argparse.ArgumentParser(description="Capture camera frames for YOLO dataset collection.")
    parser.add_argument("--source", default="0", help="Camera index, /dev/videoX, or stream URL.")
    parser.add_argument("--output", default="datasets/drone_target/images/raw")
    parser.add_argument("--prefix", default="target")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--interval", type=float, default=0.2, help="Seconds between saved images.")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source, cv2.CAP_V4L2 if isinstance(source, int) else cv2.CAP_ANY)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if args.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))

    if not cap.isOpened():
        raise SystemExit(f"Could not open camera source: {args.source}")

    saved = 0
    started = time.time()
    try:
        while saved < args.count:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("frame read failed, retrying", flush=True)
                time.sleep(0.1)
                continue

            stamp = time.strftime("%Y%m%d_%H%M%S")
            millis = int((time.time() % 1) * 1000)
            path = output / f"{args.prefix}_{stamp}_{millis:03d}_{saved:05d}.jpg"
            cv2.imwrite(str(path), frame)
            saved += 1
            print(f"saved {saved}/{args.count}: {path}", flush=True)
            time.sleep(args.interval)
    finally:
        cap.release()

    elapsed = time.time() - started
    print(f"done saved={saved} seconds={elapsed:.1f}")


if __name__ == "__main__":
    main()
