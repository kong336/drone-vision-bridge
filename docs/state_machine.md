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
  --mavlink-serial /dev/ttyUSB0 \
  --mavlink-baud 57600 \
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

On the inspected STM32MP257, only `/dev/ttySTM0` was visible and it was used by `serial-getty@ttySTM0.service`. No `/dev/ttyACM*` or `/dev/ttyUSB*` flight controller device was present. That matches an unpowered flight controller, a disconnected cable, or a non-USB wiring path that has not been mapped yet.

