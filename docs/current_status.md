# Current Status

Updated: 2026-06-04

## Jetson

Current preview:

```text
http://100.88.97.62:8090/
```

Current TensorRT engine:

```text
/home/nvidia/vision_starter/models/wrench_public_neg_320_fp16.engine
```

Current systemd state:

```text
jetson-vision.service active
vision-coco-depth.service disabled
```

Current service override:

```text
UDP_HOST=100.88.127.115
UDP_PORT=5005
UDP_RATE=20
ENGINE=models/wrench_public_neg_320_fp16.engine
LABEL=wrench
CONF=0.45
```

The old 24-image wrench model overfit badly. It false-detected all 60 captured negative background images. The current model was trained with public wrench data plus local negative background images and produced zero detections on those 60 negative images during the local check.

## STM32MP257

Current blocker:

```text
100.88.127.115 stm32mp257 offline in Tailscale
PC -> MP257 SSH timeout
Jetson -> MP257 SSH timeout
```

When MP257 is online:

```powershell
cd C:\Users\allen\drone-vision-bridge
.\deployment\status_snapshot.ps1
.\deployment\bench_validate_after_mp257_online.ps1
```

## Dry-Run Control Chain

Implemented chain:

```text
Jetson UDP JSON
  -> MP257 udp_detection_receiver.py
  -> /root/vision_comm/latest_udp.json
  -> mission_state_machine.py
  -> /root/vision_comm/latest_decision.json
  -> arm_dry_run_monitor.py
  -> /root/vision_comm/latest_arm_action.json
```

No code drives servos, arms the aircraft, sends MAVLink movement commands, or closes a gripper.

Added local runtime contracts and preflight checks:

```text
schemas/vision_latest.schema.json
schemas/uwb_aoa.schema.json
schemas/mission_decision.schema.json
schemas/arm_action.schema.json
tools/validate_json_file.py
mp257/preflight_check.py
mp257/arm_servo_config.example.json
```

## Safety Gates

The state machine requires:

```text
3 stable target frames before VISION_LOCK
5 centered frames before FINE_ALIGN
8 grab-distance frames before GRAB_DRY_RUN
MAVLink heartbeat when --require-flight is enabled
FAILSAFE if MAVLink says armed
default service MAVLink serial discovery uses auto by-id ArduPilot/PX4 lookup
```

The manipulator dry-run monitor also requires this manual enable file before it maps `GRAB_DRY_RUN` to `would_close_gripper`:

```text
/root/vision_comm/ENABLE_ARM_DRY_RUN
```

Without that file, it outputs:

```text
blocked_requires_enable_file
```

## Local Tests

Run:

```powershell
cd C:\Users\allen\drone-vision-bridge
.\tests\run_local_tests.ps1
```

This covers:

```text
mission replay state gates
UDP receiver roundtrip
MAVLink HEARTBEAT probe with fake disarmed and armed packets
local UDP -> state machine -> arm dry-run simulation
fake disarmed MAVLink heartbeat in the full-stack simulation
```
