#!/bin/sh
set -eu

cd /home/nvidia/vision_starter

UDP_HOST="${UDP_HOST:-stm32mp257}"
UDP_PORT="${UDP_PORT:-5005}"
UDP_RATE="${UDP_RATE:-10}"
ENGINE="${ENGINE:-models/yolov8n_320_fp16.engine}"
LABEL="${LABEL:-coco}"
CONF="${CONF:-0.15}"
DEPTH_JSON="${DEPTH_JSON:-/tmp/orbbec_depth_grid.json}"

PIDS="$(pgrep -f 'python3 scripts/trt_yolo_server.py' || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
fi

SOURCE_ID="$(python3 - <<'PY'
import cv2, time
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

nohup python3 scripts/trt_yolo_server.py \
  --source "$SOURCE_ID" \
  --host 0.0.0.0 \
  --port 8090 \
  --engine "$ENGINE" \
  --udp-host "$UDP_HOST" \
  --udp-port "$UDP_PORT" \
  --udp-rate "$UDP_RATE" \
  --width 640 \
  --height 480 \
  --camera-fps 30 \
  --display-fps 30 \
  --infer-fps 0 \
  --fourcc MJPG \
  --quality 65 \
  --label "$LABEL" \
  --conf "$CONF" \
  --depth-json "$DEPTH_JSON" \
  --depth-max-age 2.0 \
  > logs/trt_yolo_server.log 2>&1 < /dev/null &
echo "source=$SOURCE_ID pid=$!"
