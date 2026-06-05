# Protocol Notes

## Jetson Vision UDP

The Jetson sends one JSON object per UDP datagram. Typical fields:

```json
{
  "valid": true,
  "status": "ok",
  "source": "0",
  "timestamp": 1780117200.0,
  "image": {"w": 640, "h": 480, "center_x": 320, "center_y": 240},
  "fps": 38.0,
  "target": {
    "class": "person",
    "conf": 0.82,
    "box": {"x": 250, "y": 180, "w": 120, "h": 90},
    "center": {"x": 310, "y": 225},
    "offset": {"dx": -10, "dy": -15},
    "distance_m": 1.37
  },
  "detections": []
}
```

`dx` and `dy` are pixel offsets from the image center. The MP257 can use them for slow visual alignment after coarse positioning.

## MP257 Mission Decision JSON

The MP257 state machine writes a filtered decision to:

```text
/root/vision_comm/latest_decision.json
```

Example:

```json
{
  "time": 1780568897.034,
  "state": "GRAB_DRY_RUN",
  "reason": "target is stably within dry-run grab distance",
  "command": {"arm": "would_grab"},
  "context": {
    "vision_lock_count": 16,
    "centered_count": 13,
    "grab_ready_count": 8
  },
  "vision": {
    "ok": true,
    "age_sec": 0.08,
    "class": "wrench",
    "conf": 0.96,
    "distance_m": 0.4,
    "dx": 4,
    "dy": 0
  },
  "uwb": {
    "ok": true,
    "age_sec": 0.12,
    "distance_m": 0.98,
    "azimuth_deg": -39,
    "elevation_deg": 13
  },
  "flight": {
    "ok": true,
    "age_sec": 0.1,
    "armed": false,
    "system_status": 3
  }
}
```

Downstream manipulator code should consume this file instead of raw Jetson detections. It already includes safety gating:

```text
3 stable target frames
5 centered frames
8 grab-distance frames
fresh UWB/AOA can only drive dry-run coarse approach/search before vision lock
MAVLink disarmed check when --require-flight is enabled
```

## MP257 Manipulator Dry-Run JSON

The dry-run manipulator monitor writes:

```text
/root/vision_comm/latest_arm_action.json
```

Default blocked output:

```json
{
  "time": 1780569000.0,
  "arm_dry_run": {
    "mode": "blocked_requires_enable_file",
    "reason": "stable grab decision present, but manipulator dry-run enable file is missing",
    "enable_file": "/root/vision_comm/ENABLE_ARM_DRY_RUN"
  }
}
```

Only after the enable file exists can `GRAB_DRY_RUN` map to:

```json
{
  "arm_dry_run": {
    "mode": "would_close_gripper",
    "reason": "state machine confirmed stable target in grab range"
  }
}
```

This still does not drive servos. It is the last dry-run handoff before adding real actuator output. A close but off-center target stays in visual alignment; it is not promoted to grab readiness until it is centered for the configured number of frames.

Machine-readable JSON schema files live in:

```text
schemas/vision_latest.schema.json
schemas/uwb_aoa.schema.json
schemas/mission_decision.schema.json
schemas/arm_action.schema.json
```

They are intentionally simple enough to validate with:

```bash
python3 /root/vision_comm/validate_json_file.py \
  --schema /root/vision_comm/schemas/mission_decision.schema.json \
  /root/vision_comm/latest_decision.json
```

## ALX-AOA-FIT UART

Serial settings:

```text
115200 baud, 8 data bits, 1 stop bit, no parity, no flow control
```

Location frame command: `0x2001`.

Important fields:

```text
MessageHeader: FF FF FF FF
Distance:      uint32, cm
Azimuth:       int16, degrees
Elevation:     int16, degrees
XorByte:       XOR checksum over previous bytes
```

The parser in `mp257/uwb_aoa_reader.py` emits JSON:

```json
{
  "ok": true,
  "cmd": "location",
  "distance_m": 0.98,
  "azimuth_deg": -39,
  "elevation_deg": 13
}
```

When started with `--latest /root/vision_comm/latest_uwb.json`, valid location frames are also written to a latest-file for the state machine:

```bash
python3 /root/vision_comm/uwb_aoa_reader.py \
  --serial /dev/ttySTM1 \
  --baud 115200 \
  --latest /root/vision_comm/latest_uwb.json
```
