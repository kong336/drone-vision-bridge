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
