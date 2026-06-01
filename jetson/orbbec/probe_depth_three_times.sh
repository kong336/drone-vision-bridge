#!/bin/sh
set -eu

PIDS="$(pgrep -f 'python3 scripts/trt_yolo_server.py' || true)"
if [ -n "$PIDS" ]; then
  echo "stopping:$PIDS"
  kill $PIDS 2>/dev/null || true
fi
sleep 2

cd /home/nvidia/orbbec_sdk
printf '%s\n' nvidia | sudo -S chmod 666 /dev/bus/usb/001/* 2>/dev/null || true
for n in 1 2 3; do
  echo "--- probe $n ---"
  LD_LIBRARY_PATH=/home/nvidia/orbbec_sdk/v1/OrbbecSDK_v1.10.35/SDK/lib:${LD_LIBRARY_PATH:-} \
    timeout 20 ./depth_center_json 60 2>&1 | tail -n 8
  sleep 1
done
