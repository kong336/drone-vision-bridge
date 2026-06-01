#!/bin/sh
set -eu

echo "--- receiver service ---"
systemctl --no-pager --plain status vision-udp-receiver.service 2>/dev/null | sed -n '1,80p' || true
echo "--- process ---"
ps | grep -E 'udp_detection_receiver.py' | grep -v grep || true
echo "--- latest file ---"
ls -l /root/vision_comm/latest_udp.json 2>/dev/null || true
python3 - <<'PY'
import json
from pathlib import Path

path = Path("/root/vision_comm/latest_udp.json")
if not path.exists():
    print("missing latest_udp.json")
    raise SystemExit
msg = json.loads(path.read_text())
print(json.dumps({
    "valid": msg.get("valid"),
    "target": msg.get("target"),
    "distance_m": msg.get("distance_m"),
    "distance_method": msg.get("distance_method"),
    "fps": msg.get("fps"),
    "depth_age": (msg.get("depth") or {}).get("age_sec"),
    "received": msg.get("_received"),
}, ensure_ascii=False, indent=2))
PY
