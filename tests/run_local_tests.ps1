$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

Write-Host "== Python syntax =="
python -m py_compile `
  "$repo\mp257\mission_state_machine.py" `
  "$repo\mp257\arm_dry_run_monitor.py" `
  "$repo\mp257\preflight_check.py" `
  "$repo\mp257\udp_detection_receiver.py" `
  "$repo\mp257\uwb_aoa_reader.py" `
  "$repo\mp257\poll_latest.py" `
  "$repo\mp257\flight_link_probe.py" `
  "$repo\tools\replay_vision_udp.py" `
  "$repo\tools\fake_mavlink_heartbeat.py" `
  "$repo\tools\write_fake_uwb_latest.py" `
  "$repo\tools\validate_json_file.py" `
  "$repo\tests\test_mission_state_machine.py" `
  "$repo\tests\test_runtime_json_contracts.py" `
  "$repo\tests\test_preflight_check.py"

Write-Host "== Mission replay assertions =="
python "$repo\tests\test_mission_state_machine.py"

Write-Host "== Runtime JSON contracts =="
python "$repo\tests\test_runtime_json_contracts.py"

Write-Host "== MP257 preflight offline smoke =="
python "$repo\mp257\preflight_check.py" --root "$repo\tests" --arm-servo-config "$repo\mp257\arm_servo_config.example.json"

Write-Host "== MP257 preflight assertions =="
python "$repo\tests\test_preflight_check.py"

Write-Host "== UDP receiver roundtrip =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_udp_receiver_roundtrip.ps1"

Write-Host "== MAVLink heartbeat probe =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_mavlink_heartbeat_probe.ps1"

Write-Host "== UWB/AOA parser =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_uwb_aoa_reader.ps1"

Write-Host "== Fake UWB latest =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_fake_uwb_latest.ps1"

Write-Host "== Local UWB stack simulation =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_local_uwb_stack.ps1"

Write-Host "== Local full stack simulation =="
powershell -ExecutionPolicy Bypass -File "$repo\tests\test_local_full_stack.ps1"

Write-Host "All local tests passed."
