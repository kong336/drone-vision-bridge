#!/bin/sh
set -eu

JETSON_HEALTH_URL="${JETSON_HEALTH_URL:-http://jetson-xavier:8090/healthz}"
VISION_LATEST="${VISION_LATEST:-/root/vision_comm/latest_udp.json}"
DECISION_LATEST="${DECISION_LATEST:-/root/vision_comm/latest_decision.json}"
ARM_ACTION_LATEST="${ARM_ACTION_LATEST:-/root/vision_comm/latest_arm_action.json}"
UWB_LATEST="${UWB_LATEST:-/root/vision_comm/latest_uwb.json}"
VISION_MAX_AGE="${VISION_MAX_AGE:-2.0}"
DECISION_MAX_AGE="${DECISION_MAX_AGE:-2.0}"
ARM_ACTION_MAX_AGE="${ARM_ACTION_MAX_AGE:-2.0}"
UWB_MAX_AGE="${UWB_MAX_AGE:-2.0}"
MAVLINK_SERIAL="${MAVLINK_SERIAL:-}"
MAVLINK_BAUD="${MAVLINK_BAUD:-115200}"
MAVLINK_SECONDS="${MAVLINK_SECONDS:-2}"

FAIL=0

check() {
  name="$1"
  shift
  if "$@"; then
    printf '[OK] %s\n' "$name"
  else
    printf '[FAIL] %s\n' "$name"
    FAIL=1
  fi
}

service_active() {
  systemctl is-active --quiet "$1"
}

jetson_health() {
  JETSON_HEALTH_URL="$JETSON_HEALTH_URL" python3 - <<'PY'
import os
import urllib.request

url = os.environ["JETSON_HEALTH_URL"]
with urllib.request.urlopen(url, timeout=3) as resp:
    body = resp.read().decode("utf-8", "replace")
if '"status":"ok"' not in body and '"status": "ok"' not in body:
    raise SystemExit(body[:200])
print(body[:200])
PY
}

vision_latest_fresh() {
  VISION_LATEST="$VISION_LATEST" VISION_MAX_AGE="$VISION_MAX_AGE" python3 - <<'PY'
import json
import os
import time

path = os.environ["VISION_LATEST"]
max_age = float(os.environ["VISION_MAX_AGE"])
msg = json.load(open(path))
received = (msg.get("_received") or {}).get("time", msg.get("timestamp"))
if received is None:
    raise SystemExit("no received timestamp")
age = time.time() - float(received)
source = (msg.get("_received") or {}).get("from")
status = msg.get("status")
fps = msg.get("fps")
print(f"status={status} source={source} age_sec={age:.3f} fps={fps}")
if status != "ok" or age > max_age:
    raise SystemExit(1)
PY
}

decision_latest_fresh() {
  DECISION_LATEST="$DECISION_LATEST" DECISION_MAX_AGE="$DECISION_MAX_AGE" python3 - <<'PY'
import json
import os
import time

path = os.environ["DECISION_LATEST"]
max_age = float(os.environ["DECISION_MAX_AGE"])
msg = json.load(open(path))
timestamp = msg.get("time")
if timestamp is None:
    raise SystemExit("no decision time")
age = time.time() - float(timestamp)
print(f"state={msg.get('state')} age_sec={age:.3f} reason={msg.get('reason')}")
if age > max_age:
    raise SystemExit(1)
PY
}

arm_action_latest_fresh() {
  ARM_ACTION_LATEST="$ARM_ACTION_LATEST" ARM_ACTION_MAX_AGE="$ARM_ACTION_MAX_AGE" python3 - <<'PY'
import json
import os
import time

path = os.environ["ARM_ACTION_LATEST"]
max_age = float(os.environ["ARM_ACTION_MAX_AGE"])
msg = json.load(open(path))
timestamp = msg.get("time")
if timestamp is None:
    raise SystemExit("no arm action time")
age = time.time() - float(timestamp)
action = msg.get("arm_dry_run") or {}
print(f"mode={action.get('mode')} age_sec={age:.3f} reason={action.get('reason')}")
if age > max_age:
    raise SystemExit(1)
PY
}

mavlink_ok() {
  if [ -z "$MAVLINK_SERIAL" ]; then
    MAVLINK_SERIAL="$(find /dev/serial/by-id -maxdepth 1 -type l -name '*ArduPilot*' 2>/dev/null | sort | head -n 1 || true)"
  fi
  if [ ! -e "$MAVLINK_SERIAL" ]; then
    printf 'missing MAVLink serial; set MAVLINK_SERIAL=/dev/serial/by-id/...\n'
    return 1
  fi
  REPORT_JSON="$(python3 /root/vision_comm/flight_link_probe.py \
    --serial "$MAVLINK_SERIAL" \
    --baud "$MAVLINK_BAUD" \
    --seconds "$MAVLINK_SECONDS")"
  REPORT_JSON="$REPORT_JSON" python3 - <<'PY'
import json
import os
import sys

report = json.loads(os.environ["REPORT_JSON"])
mav = report.get("mavlink") or {}
print(f"ok={mav.get('ok')} armed={mav.get('armed')} system_status={mav.get('system_status')}")
if not mav.get("ok"):
    raise SystemExit(1)
if mav.get("armed") is True:
    raise SystemExit("flight controller is armed")
PY
}

state_machine_has_flight() {
  journalctl -u mp257-mission-state-machine.service -n 20 --no-pager | grep -q '"flight": {"ok": true'
}

printf 'Full stack health check\n'
printf 'Jetson health URL: %s\n' "$JETSON_HEALTH_URL"
printf 'Vision latest: %s\n' "$VISION_LATEST"
printf 'Decision latest: %s\n' "$DECISION_LATEST"
printf 'Arm action latest: %s\n' "$ARM_ACTION_LATEST"
printf 'UWB latest: %s\n' "$UWB_LATEST"
printf 'MAVLink serial: %s\n\n' "${MAVLINK_SERIAL:-auto ArduPilot by-id}"

check "vision UDP receiver service active" service_active vision-udp-receiver.service
check "mission state machine service active" service_active mp257-mission-state-machine.service
check "arm dry-run monitor service active" service_active mp257-arm-dry-run.service
check "Jetson health endpoint reachable" jetson_health
check "fresh Jetson UDP vision packet" vision_latest_fresh
check "fresh mission decision" decision_latest_fresh
check "fresh arm dry-run action" arm_action_latest_fresh
check "MAVLink heartbeat present and disarmed" mavlink_ok
check "state machine journal sees flight.ok=true" state_machine_has_flight
check "read-only preflight summary" python3 /root/vision_comm/preflight_check.py \
  --root /root/vision_comm \
  --jetson-health-url "$JETSON_HEALTH_URL" \
  --mavlink-serial "${MAVLINK_SERIAL:-}" \
  --mavlink-baud "$MAVLINK_BAUD" \
  --vision-max-age "$VISION_MAX_AGE" \
  --decision-max-age "$DECISION_MAX_AGE" \
  --arm-action-max-age "$ARM_ACTION_MAX_AGE" \
  --uwb-latest "$UWB_LATEST" \
  --uwb-max-age "$UWB_MAX_AGE" \
  --require-live \
  --require-services \
  --require-jetson \
  --require-mavlink

exit "$FAIL"
