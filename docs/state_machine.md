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
python3 /root/vision_comm/mission_state_machine.py --period 0.2
```

If a MAVLink telemetry stream is available later:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --mavlink-serial /dev/serial/by-id/YOUR_FLIGHT_CONTROLLER \
  --mavlink-baud 115200 \
  --require-flight
```

or UDP heartbeat:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --mavlink-udp-port 14550 \
  --require-flight
```

## Safety Rules

- If `--require-flight` is set and no MAVLink heartbeat is seen, the state stays in `WAIT_FLIGHT_SAFE`.
- If the flight controller is already armed, the state switches to `FAILSAFE`.
- Commands are printed as `dry_run_velocity` or `dry_run_coarse_velocity`; no MAVLink control messages are sent.
- Arm, takeoff, land, gripper, and actuator commands must be added only after bench testing and with RC/manual takeover ready.

## Current Board Finding

When a CUAV flight controller is powered over USB, the inspected STM32MP257 exposed two ACM ports:

```text
/dev/ttyACM0
/dev/ttyACM1
/dev/serial/by-id/usb-ArduPilot_CUAVv5-bdshot_...-if00
/dev/serial/by-id/usb-ArduPilot_CUAVv5-bdshot_...-if02
```

Both ACM ports produced MAVLink heartbeat during the bench check. Prefer the `/dev/serial/by-id/...` path in services because it is stable across reboots and USB re-enumeration.
