import argparse
import time
from pathlib import Path

import cv2
import numpy as np


COLOR_RANGES = {
    "red": [((0, 80, 60), (10, 255, 255)), ((170, 80, 60), (180, 255, 255))],
    "green": [((35, 60, 50), (85, 255, 255))],
    "blue": [((90, 60, 50), (130, 255, 255))],
    "yellow": [((20, 80, 80), (35, 255, 255))],
}


def parse_source(value):
    return int(value) if value.isdigit() else value


def make_mask(frame, target):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lower, upper in COLOR_RANGES[target]:
        mask |= cv2.inRange(hsv, np.array(lower), np.array(upper))
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def find_largest_target(mask, min_area):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < min_area:
        return None
    x, y, w, h = cv2.boundingRect(contour)
    return x, y, w, h, area


def main():
    parser = argparse.ArgumentParser(description="Detect a colored object and print its center point.")
    parser.add_argument("--source", default="0", help="Camera index, /dev/videoX, or stream URL.")
    parser.add_argument("--target", choices=sorted(COLOR_RANGES), default="red")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frames", type=int, default=0, help="0 means run forever.")
    parser.add_argument("--min-area", type=float, default=800.0)
    parser.add_argument("--save-every", type=int, default=30)
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source = parse_source(args.source)
    backend = cv2.CAP_V4L2 if isinstance(source, int) else cv2.CAP_ANY
    cap = cv2.VideoCapture(source, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    if not cap.isOpened():
        raise SystemExit(f"Could not open camera source: {args.source}")

    print("time,target,found,cx,cy,w,h,area", flush=True)
    count = 0
    while args.frames == 0 or count < args.frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise SystemExit("Camera opened, but frame read failed.")

        count += 1
        mask = make_mask(frame, args.target)
        result = find_largest_target(mask, args.min_area)
        annotated = frame.copy()

        if result:
            x, y, w, h, area = result
            cx = x + w // 2
            cy = y + h // 2
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(annotated, (cx, cy), 5, (0, 0, 255), -1)
            print(f"{time.time():.3f},{args.target},1,{cx},{cy},{w},{h},{area:.1f}", flush=True)
        else:
            print(f"{time.time():.3f},{args.target},0,-1,-1,0,0,0", flush=True)

        if args.save_every and count % args.save_every == 0:
            cv2.imwrite(str(out_dir / "detect_latest.jpg"), annotated)

    cap.release()


if __name__ == "__main__":
    main()
