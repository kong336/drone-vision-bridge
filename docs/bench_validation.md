# Bench Validation Runbook

Use this after the STM32MP257 is online again. Keep props off and the aircraft disarmed.

## 1. Local PC Tests

```powershell
cd C:\Users\allen\drone-vision-bridge
.\tests\run_local_tests.ps1
```

This verifies:

- state machine replay safety gates
- UDP receiver JSON roundtrip
- local UDP -> state machine -> arm dry-run handoff

## 2. Board Link Check

```powershell
.\deployment\check_tailscale_links.ps1
```

Expected:

- PC -> Jetson SSH works
- PC -> MP257 SSH works
- Jetson -> MP257 SSH works after key install

For a read-only snapshot that does not deploy anything:

```powershell
.\deployment\status_snapshot.ps1
```

## 3. One-Command Bench Deploy

```powershell
.\deployment\bench_validate_after_mp257_online.ps1
```

This runs the local safety tests, takes a read-only status snapshot, deploys MP257 scripts and services, then runs health checks.

If the UWB/AOA UART path has already been confirmed:

```powershell
.\deployment\bench_validate_after_mp257_online.ps1 -EnableUwbService
```

## 4. Required Before Physical Motion

- `jetson-vision.service` active
- `vision-coco-depth.service` disabled
- `vision-udp-receiver.service` active
- `mp257-mission-state-machine.service` active
- `mp257-arm-dry-run.service` active
- `latest_udp.json` fresh
- `latest_decision.json` fresh
- `latest_arm_action.json` fresh
- `latest_uwb.json` fresh if UWB/AOA is part of the bench test
- MAVLink heartbeat present
- flight controller disarmed
- `flight_link_probe.py --serial auto` finds a by-id flight controller path, or the state machine remains in `WAIT_FLIGHT_SAFE`

Do not add servo, gripper, arming, takeoff, or movement output until this bench checklist passes repeatedly.

The manipulator dry-run monitor is guarded by:

```text
/root/vision_comm/ENABLE_ARM_DRY_RUN
```

Do not create that file until bench tests are intentionally checking the final dry-run close-gripper decision.

## Optional UWB/AOA Simulation

Without UWB hardware, you can still check the coarse-position branch:

```bash
python3 /root/vision_comm/write_fake_uwb_latest.py \
  --latest /root/vision_comm/latest_uwb.json \
  --distance-m 3.2 \
  --azimuth-deg 30 \
  --seconds 10
```

With MAVLink required, the state machine must still stay in `WAIT_FLIGHT_SAFE` until a disarmed heartbeat is present.

The PC test suite includes the same idea as a process-level test:

```powershell
.\tests\test_local_uwb_stack.ps1
```
