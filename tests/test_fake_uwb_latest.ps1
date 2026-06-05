$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$latest = Join-Path $env:TEMP "drone_vision_fake_uwb_latest.json"
if (Test-Path -LiteralPath $latest) {
    Remove-Item -LiteralPath $latest -Force
}

python "$repo\tools\write_fake_uwb_latest.py" --latest $latest --distance-m 3.2 --azimuth-deg 30 | Out-Host
python "$repo\tools\validate_json_file.py" --schema "$repo\schemas\uwb_aoa.schema.json" $latest

$decision = python "$repo\mp257\mission_state_machine.py" `
  --vision-latest "$repo\tests\missing_vision.json" `
  --uwb-latest $latest `
  --mavlink-udp-port 5021 `
  --require-flight `
  --once | ConvertFrom-Json

if ($decision.state -ne "WAIT_FLIGHT_SAFE") {
    throw "without heartbeat, expected WAIT_FLIGHT_SAFE, got $($decision.state)"
}

$decisionNoFlightGate = python "$repo\mp257\mission_state_machine.py" `
  --vision-latest "$repo\tests\missing_vision.json" `
  --uwb-latest $latest `
  --once | ConvertFrom-Json

if ($decisionNoFlightGate.state -ne "UWB_APPROACH") {
    throw "without flight gate, expected UWB_APPROACH, got $($decisionNoFlightGate.state)"
}

Write-Host "OK fake UWB latest drives state=$($decisionNoFlightGate.state) when flight gate is disabled"
