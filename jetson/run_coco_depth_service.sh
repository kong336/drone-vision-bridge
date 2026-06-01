#!/bin/sh
set -eu

cd /home/nvidia/vision_starter

UDP_HOST="${UDP_HOST:-192.168.1.175}"
UDP_PORT="${UDP_PORT:-5005}"
ENGINE="${ENGINE:-models/yolov8n_320_fp16.engine}"
DEPTH_JSON="${DEPTH_JSON:-/tmp/orbbec_depth_grid.json}"

SOURCE_ID="$(python3 - <<'PY'
import cv2
import time

for src in range(8):
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
    ok = False
    if cap.isOpened():
        for _ in range(8):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.1)
    cap.release()
    if ok:
        print(src)
        raise SystemExit
print(0)
PY
)"

exec /usr/bin/python3 scripts/trt_yolo_server.py \
  --source "$SOURCE_ID" \
  --host 0.0.0.0 \
  --port 8090 \
  --engine "$ENGINE" \
  --udp-host "$UDP_HOST" \
  --udp-port "$UDP_PORT" \
  --udp-rate 20 \
  --width 640 \
  --height 480 \
  --camera-fps 30 \
  --display-fps 30 \
  --infer-fps 0 \
  --fourcc MJPG \
  --quality 65 \
  --label coco \
  --conf 0.15 \
  --depth-json "$DEPTH_JSON" \
  --depth-max-age 2.0
