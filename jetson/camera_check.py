import argparse
import time
from pathlib import Path

import cv2


def parse_source(value):
    return int(value) if value.isdigit() else value


def open_camera(source, width, height, fps):
    backend = cv2.CAP_V4L2 if isinstance(source, int) else cv2.CAP_ANY
    cap = cv2.VideoCapture(source, backend)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps:
        cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def main():
    parser = argparse.ArgumentParser(description="Headless camera smoke test.")
    parser.add_argument("--source", default="0", help="Camera index, /dev/videoX, or stream URL.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frames", type=int, default=120, help="0 means run forever.")
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source = parse_source(args.source)
    cap = open_camera(source, args.width, args.height, args.fps)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera source: {args.source}")

    count = 0
    started = time.time()
    last_report = started

    while args.frames == 0 or count < args.frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise SystemExit("Camera opened, but frame read failed.")

        count += 1
        cv2.imwrite(str(out_dir / "camera_latest.jpg"), frame)

        now = time.time()
        if now - last_report >= 1.0:
            elapsed = now - started
            actual_fps = count / elapsed if elapsed else 0.0
            h, w = frame.shape[:2]
            print(f"frames={count} size={w}x{h} avg_fps={actual_fps:.1f}", flush=True)
            last_report = now

    cap.release()
    elapsed = time.time() - started
    print(f"done frames={count} seconds={elapsed:.2f} avg_fps={count / elapsed:.1f}")
    print(f"latest frame: {out_dir / 'camera_latest.jpg'}")


if __name__ == "__main__":
    main()
