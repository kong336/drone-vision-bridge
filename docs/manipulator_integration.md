# Manipulator Integration Plan

This project currently stops at dry-run manipulator actions. That is intentional.

## Current Handoff

```text
Jetson vision JSON
  -> MP257 latest_udp.json
  -> mission_state_machine.py
  -> latest_decision.json
  -> arm_dry_run_monitor.py
  -> latest_arm_action.json
```

The manipulator should not consume raw detections. It should consume `latest_arm_action.json`.

For alignment before a grab, the lower-level controller can also inspect the filtered vision packet at `/root/vision_comm/latest_udp.json`. The useful target fields are:

```text
target.offset.dx/dy             pixel error from image center
target.distance_m               target depth in meters
target.position_camera_m.x/y/z  target camera-frame coordinates in meters
```

Use `dx/dy` for simple image-center alignment and `position_camera_m` for a future Cartesian controller. The current `position_camera_m` output is camera-frame only; it is not yet transformed into drone body frame or manipulator base frame. That transform needs camera mounting geometry before it can drive an arm safely.

## Close-Range Handoff

Do not rely on pure 2D detection all the way into contact. The practical chain
for the wrench task is:

```text
far / mid range:
  RGB YOLO detects wrench at about 30 FPS
  image error drives slow XY centering
  Orbbec depth gives approximate z

near range:
  use the last stable RGB+depth pose
  transform through hand-eye calibration into the arm base frame
  execute a short guarded approach sequence
  stop using the detector as the sole truth once the target is too close or
  partially outside the image
```

The Jetson-side hand-eye prototype in `Dual_Camera_HandEye` already follows
that shape:

```text
latest.json -> fused_wrench_pose_latest.json -> wrench_grasp_sequence_latest.json
```

`wrench_image_follow_preview.py` is only a sign/gain checker. It outputs small
proposed XY steps and does not open a servo port. Use it to confirm direction
before any real motion.

For smoother video and steadier control, keep the browser stream lower than the
inference loop:

```text
infer_fps=30
display_fps=15-20
max_detections=1
capture_thread=enabled
```

Control should consume `/latest.json`, not the browser stream. Browser MJPEG
smoothness is a debugging comfort metric; the control signal should be judged
by timestamp freshness, FPS, confidence, and pose stability.

The Jetson service publishes both the raw detector target and an optional
EMA-smoothed control target:

```text
target           raw YOLO output
target_smoothed  filtered center, offset, depth, and camera-frame position
```

The MP257 state machine reads `target_smoothed` first and falls back to
`target` when the smoothed field is absent. This steadies arm follow while
keeping raw detections available for debugging and model checks.

## Current Safety Gates

- target class must match `wrench`
- confidence must be above threshold
- target must persist for multiple frames
- target must be centered for multiple frames
- target must remain within grab distance for multiple frames
- if MAVLink is required, heartbeat must be present
- if MAVLink reports armed, state goes to `FAILSAFE`
- dry-run close-gripper output is blocked until `/root/vision_comm/ENABLE_ARM_DRY_RUN` exists

## Next Physical Bench Step

Before any servo signal is added:

1. Keep propellers removed.
2. Keep the flight controller disarmed.
3. Run `tests/run_local_tests.ps1` on the PC.
4. Bring MP257 online.
5. Run `deployment/bench_validate_after_mp257_online.ps1`.
6. Confirm `latest_arm_action.json` stays in `hold`, `track_only`, or `blocked_requires_enable_file`.
7. Create `/root/vision_comm/ENABLE_ARM_DRY_RUN` only for a dry-run close-gripper decision test.

## Future Real Actuator Output

When hardware wiring is known, add a separate process such as:

```text
arm_servo_controller.py
```

That process should:

- read `latest_arm_action.json`
- refuse stale action files
- refuse action unless an explicit enable file exists
- clamp every servo pulse to configured min/max
- start in neutral/open pose
- log every commanded position
- support a hardware kill switch or manual power removal

Do not put servo output inside the vision process or the state machine. Keeping it separate makes it easier to stop and audit.

## Servo Config Template

The repository includes:

```text
mp257/arm_servo_config.example.json
```

Keep `enabled` as `false` until the manipulator is tested on a bench with propellers removed and current-limited power. The template records the pulse bounds, open/close positions, stale-action timeout, and a separate real-output enable file. It is intentionally only a contract for future hardware output; no current script sends servo PWM.

Run the read-only preflight checker before any bench test:

```bash
python3 /root/vision_comm/preflight_check.py \
  --root /root/vision_comm \
  --jetson-health-url http://100.88.97.62:8090/healthz \
  --require-live \
  --require-services
```
