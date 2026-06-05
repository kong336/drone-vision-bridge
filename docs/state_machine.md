# Mission State Machine

This state machine is intentionally monitor-only by default. It reads Jetson vision packets, optional UWB/AOA packets, and optional MAVLink heartbeats, then prints the action it would take. It does not arm the aircraft and does not send movement commands.

## States

```text
BOOT
WAIT_LINKS
WAIT_FLIGHT_SAFE
IDLE_SAFE
UWB_SEARCH
UWB_APPROACH
VISION_LOCK
FINE_ALIGN
GRAB_READY
GRAB_DRY_RUN
HOLD
FAILSAFE
```

## Intended Use

Run on the STM32MP257:

```bash
python3 /root/vision_comm/mission_state_machine.py --once
```

Continuous monitor:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --uwb-latest /root/vision_comm/latest_uwb.json \
  --period 0.2 \
  --decision-latest /root/vision_comm/latest_decision.json
```

Offline replay from the repo, useful before the MP257 is online:

```bash
python3 mp257/mission_state_machine.py \
  --replay tests/mission_replay_scenarios.jsonl \
  --require-flight
```

If a MAVLink telemetry stream is available later:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --mavlink-serial auto \
  --mavlink-baud 115200 \
  --require-flight
```

`--mavlink-serial auto` searches `/dev/serial/by-id/*ArduPilot*` and `/dev/serial/by-id/*PX4*`. If the device is not found, the state machine does not crash; with `--require-flight` it remains in `WAIT_FLIGHT_SAFE`.

or UDP heartbeat:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --mavlink-udp-port 14550 \
  --require-flight
```

## Safety Rules

- If `--require-flight` is set and no MAVLink heartbeat is seen, the state stays in `WAIT_FLIGHT_SAFE`.
- If the flight controller is already armed, the state switches to `FAILSAFE`.
- A single vision detection is not enough to trigger action. Defaults require 3 stable target frames, then 5 centered frames, then 8 centered grab-distance frames before `GRAB_DRY_RUN`.
- If UWB/AOA is fresh but vision has no target, the state can only produce dry-run coarse approach/search commands.
- Commands are printed as `dry_run_velocity` or `dry_run_coarse_velocity`; no MAVLink control messages are sent.
- Arm, takeoff, land, gripper, and actuator commands must be added only after bench testing and with RC/manual takeover ready.

## Manipulator Handoff

The state machine can write a filtered decision file:

```text
/root/vision_comm/latest_decision.json
```

The dry-run manipulator monitor reads that file:

```bash
python3 /root/vision_comm/arm_dry_run_monitor.py --once
```

By default it requires this manual enable file before it will print `would_close_gripper`:

```text
/root/vision_comm/ENABLE_ARM_DRY_RUN
```

Without that file, a stable `GRAB_DRY_RUN` decision maps to `blocked_requires_enable_file`. It does not drive servos.

## Current Board Finding

When a CUAV flight controller is powered over USB, the inspected STM32MP257 exposed two ACM ports:

```text
/dev/ttyACM0
/dev/ttyACM1
/dev/serial/by-id/usb-ArduPilot_CUAVv5-bdshot_...-if00
/dev/serial/by-id/usb-ArduPilot_CUAVv5-bdshot_...-if02
```

Both ACM ports produced MAVLink heartbeat during the bench check. Prefer the `/dev/serial/by-id/...` path in services because it is stable across reboots and USB re-enumeration. The provided systemd service defaults to `MAVLINK_SERIAL=auto` so it uses a stable by-id path when available.
