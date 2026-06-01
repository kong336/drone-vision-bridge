#!/bin/sh
set -eu

echo "--- services ---"
systemctl --no-pager --plain status orbbec-depth-grid.service vision-coco-depth.service 2>/dev/null | sed -n '1,80p' || true
echo "--- processes ---"
pgrep -af 'depth_grid_daemon|trt_yolo_server.py' || true
echo "--- usb ---"
lsusb -t
echo "--- latest ---"
python3 - <<'PY'
import json
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8090/latest.json", timeout=5) as response:
        msg = json.loads(response.read().decode())
    print(json.dumps({
        "status": msg.get("status"),
        "source": msg.get("source"),
        "fps": msg.get("fps"),
        "valid": msg.get("valid"),
        "target": msg.get("target"),
        "distance_m": msg.get("distance_m"),
        "distance_method": msg.get("distance_method"),
        "depth_age": (msg.get("depth") or {}).get("age_sec"),
    }, ensure_ascii=False, indent=2))
except Exception as exc:
    print("latest_error", repr(exc))
PY
