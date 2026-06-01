#!/usr/bin/env python3
import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def detect_color(frame, target, min_area):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lower, upper in COLOR_RANGES[target]:
        mask |= cv2.inRange(hsv, np.array(lower), np.array(upper))
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < min_area:
        return None
    x, y, w, h = cv2.boundingRect(contour)
    return x, y, w, h, area


def describe_offset(dx, dy, deadband):
    horizontal = "center"
    vertical = "center"
    if dx < -deadband:
        horizontal = "left"
    elif dx > deadband:
        horizontal = "right"
    if dy < -deadband:
        vertical = "up"
    elif dy > deadband:
        vertical = "down"
    return horizontal, vertical


def proportional_command(error, deadband, gain, limit):
    if abs(error) <= deadband:
        return 0
    command = int(round(error * gain))
    return max(-limit, min(limit, command))


def draw_detection(frame, target, min_area, deadband, gain, limit):
    height, width = frame.shape[:2]
    frame_cx = width // 2
    frame_cy = height // 2
    cv2.line(frame, (frame_cx, 0), (frame_cx, height), (255, 255, 255), 1)
    cv2.line(frame, (0, frame_cy), (width, frame_cy), (255, 255, 255), 1)
    cv2.circle(frame, (frame_cx, frame_cy), 5, (255, 255, 255), -1)

    if not target:
        return frame
    result = detect_color(frame, target, min_area)
    if not result:
        cv2.putText(frame, f"{target}: not found", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return frame

    x, y, w, h, area = result
    cx = x + w // 2
    cy = y + h // 2
    dx = cx - frame_cx
    dy = cy - frame_cy
    horizontal, vertical = describe_offset(dx, dy, deadband)
    pan = proportional_command(dx, deadband, gain, limit)
    tilt = proportional_command(dy, deadband, gain, limit)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
    cv2.line(frame, (frame_cx, frame_cy), (cx, cy), (0, 255, 255), 2)
    cv2.putText(
        frame,
        f"{target} cx={cx} cy={cy} dx={dx:+d} dy={dy:+d}",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
    )
    cv2.putText(
        frame,
        f"target: {horizontal}, {vertical}",
        (12, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
    )
    cv2.putText(
        frame,
        f"control: pan={pan:+d} tilt={tilt:+d}",
        (12, 88),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 0),
        2,
    )
    return frame


def make_handler(source, width, height, fps, quality, fourcc, target, min_area, deadband, gain, limit):
    class MjpegHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<!doctype html><title>Jetson Camera</title>"
                    b"<style>body{margin:0;background:#111;color:#eee;font-family:sans-serif}"
                    b"main{display:grid;place-items:center;min-height:100vh}"
                    b"img{max-width:100vw;max-height:100vh}</style>"
                    b"<main><img src='/stream.mjpg' alt='Jetson camera stream'></main>"
                )
                return

            if self.path != "/stream.mjpg":
                self.send_error(404)
                return

            cap = cv2.VideoCapture(source, cv2.CAP_V4L2 if isinstance(source, int) else cv2.CAP_ANY)
            if width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            if height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if fps:
                cap.set(cv2.CAP_PROP_FPS, fps)
            if fourcc:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))

            if not cap.isOpened():
                self.send_error(503, "Could not open camera")
                return

            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            delay = 1.0 / fps if fps else 0.03
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        time.sleep(0.1)
                        continue
                    frame = draw_detection(frame, target, min_area, deadband, gain, limit)
                    ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if not ok:
                        continue
                    payload = jpg.tobytes()
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(payload)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                    time.sleep(delay)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                pass
            finally:
                cap.release()

        def log_message(self, fmt, *args):
            return

    return MjpegHandler


def main():
    parser = argparse.ArgumentParser(description="Simple MJPEG camera preview server.")
    parser.add_argument("--source", default="0")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--fourcc", default="", help="Camera input format, for example MJPG or YUYV.")
    parser.add_argument("--target", choices=sorted(COLOR_RANGES), help="Draw a color detection box.")
    parser.add_argument("--min-area", type=float, default=800.0)
    parser.add_argument("--deadband", type=int, default=40, help="Pixel tolerance around the image center.")
    parser.add_argument("--gain", type=float, default=0.15, help="Control output per pixel of error.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum absolute control output.")
    args = parser.parse_args()

    source = parse_source(args.source)
    handler = make_handler(
        source,
        args.width,
        args.height,
        args.fps,
        args.quality,
        args.fourcc,
        args.target,
        args.min_area,
        args.deadband,
        args.gain,
        args.limit,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving camera {args.source} on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
