#!/bin/sh
set -eu

printf '%s\n' nvidia | sudo -S chmod 666 /dev/bus/usb/001/* 2>/dev/null || true

PIDS="$(pgrep -f '/home/nvidia/orbbec_sdk/depth_grid_daemon' || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
fi

rm -f /tmp/orbbec_depth_grid.json /tmp/orbbec_depth_grid.json.tmp
cd /home/nvidia/orbbec_sdk
nohup env LD_LIBRARY_PATH=/home/nvidia/orbbec_sdk/v1/OrbbecSDK_v1.10.35/SDK/lib:${LD_LIBRARY_PATH:-} \
  /home/nvidia/orbbec_sdk/depth_grid_daemon /tmp/orbbec_depth_grid.json 32 20 100 \
  > /home/nvidia/orbbec_sdk/depth_grid_daemon.log 2>&1 < /dev/null &
echo $!
