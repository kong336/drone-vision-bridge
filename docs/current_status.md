# Current Status

Updated: 2026-06-27

## Jetson

Current migrated Jetson preview:

```text
http://192.168.1.80:8090/
```

Current migrated Jetson latest JSON:

```text
http://192.168.1.80:8090/latest.json
```

Current migrated Jetson TensorRT engine:

```text
/home/nvidia/vision_starter/models/wrench_combined_20260626_320_trt7_fp16.engine
```

Current migrated Jetson service shape:

```text
source=/dev/video1
camera=Orbbec DaBai DCW2 RGB Camera
resolution=640x480
camera_fps=30
fourcc=MJPG
label=wrench
conf=0.25
iou=0.45
max_detections=1
depth_json=/tmp/orbbec_depth_grid.json
camera_hfov_deg=67
camera_vfov_deg=52
http_port=8090
latest_status=source /dev/video1, about 29 FPS, depth ok, fused pose valid
```

The migrated board is still an NVIDIA Jetson Xavier NX Developer Kit, but it
runs an older software stack than the previous deployment:

```text
new board: Ubuntu 18.04, JetPack 4.4.1, L4T 32.4.4, CUDA 10.2, TensorRT 7.1.3, OpenCV 3.4.5
old board: Ubuntu 20.04.6, JetPack 5.1.6, L4T 35.6.4, CUDA 11.4, TensorRT 8.5.2.2, OpenCV 4.5.4
```

This version gap matters for TensorRT engine compatibility. Engines built on
the previous JetPack 5 / TensorRT 8 stack should not be treated as portable to
this JetPack 4 / TensorRT 7 board. Keep the ONNX file as the portable artifact
and rebuild a board-local engine with the TensorRT 7 toolchain. The `trt7`
suffix on the current `wrench_combined_20260626_320_trt7_fp16.engine` is the
important compatibility marker.

Useful retained model history:

```text
wrench_public_neg_320_fp16.engine
```

The old 24-image wrench model overfit badly. It false-detected all 60 captured
negative background images. The `wrench_public_neg` model was trained with
public wrench data plus local negative background images and produced zero
detections on those 60 negative images during the local check.

```text
wrench_combined_20260626_320.onnx
wrench_combined_20260626_320_trt7_fp16.engine
```

The June 26 wrench model is the current migrated-board candidate. The useful
parts to carry forward are:

```text
public wrench positives
local wrench captures
local negative/background images
320 input export
FP16 TensorRT build on the target board
Orbbec RGB source /dev/video1
Orbbec depth grid JSON fused into latest.json
single best wrench target for control handoff
```

Jetson-side data transferred from the other training machine is under:

```text
/home/nvidia/Desktop/78arm/Dual_Camera_HandEye/yolo_training/datasets/
```

Observed dataset counts:

```text
wrench_autolabel_20260626: 30 train, 10 val
wrench_autolabel_20260626_flight_aug: 150 train, 20 val
wrench_motion_autolabel_20260626_214357: 40 train, 8 val
wrench_motion_autolabel_20260626_214357_flight_aug: 160 train, 16 val
wrench_combined_autolabel_20260626_flight_aug: 310 train, 36 val
```

The transferred labels were structurally valid YOLO labels for class `wrench`.
The available training artifacts on the Jetson are the ONNX and TensorRT engine,
not the original CPU-training `best.pt` or `runs/` metrics directory.

Latest live validation on the migrated Jetson:

```text
latest.json valid=true
target class=wrench
confidence about 0.80
rgb inference about 28.5-30 FPS
depth source=/tmp/orbbec_depth_grid.json
target distance about 0.276 m
position_camera_m present
fused_wrench_pose_latest.json valid=true
wrench_grasp_sequence_latest.json valid=true
```

Current generated dry-run grasp plan from the live pose:

```text
pregrasp x=-108.512 mm, y=-38.080 mm, z=180.000 mm
approach x=-108.512 mm, y=-38.080 mm, z=155.000 mm
grasp close at z=155.000 mm
lift z=190.000 mm
return_home z=240.000 mm
```

The image-follow preview is stable around:

```text
err=(+0.22,-0.26), z=0.276 m, step_xy_mm=(+1.3,-1.5)
```

This is still a dry-run/preview signal. It should not directly move the arm
until the physical bench safety checks and direction checks are complete.

If the old Jetson or Windows training machine still has the YOLO training run,
keep `best.pt`, the exported `.onnx`, the dataset YAML, and the train/val split.
Do not rely on the `.engine` alone; TensorRT engines are board/runtime-specific.

Previous service override retained for the JetPack 5/Tailscale deployment:

```text
UDP_HOST=100.88.127.115
UDP_PORT=5005
UDP_RATE=20
ENGINE=models/wrench_public_neg_320_fp16.engine
LABEL=wrench
CONF=0.45
```

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
