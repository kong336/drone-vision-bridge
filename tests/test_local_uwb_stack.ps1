$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$uwbLatest = Join-Path $env:TEMP "drone_vision_uwb_stack_latest_uwb.json"
$decision = Join-Path $env:TEMP "drone_vision_uwb_stack_decision.json"
$stateLog = Join-Path $env:TEMP "drone_vision_uwb_stack_state.log"

foreach ($path in @($uwbLatest, $decision, $stateLog)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$stateMachine = $null
$heartbeat = $null
$uwbWriter = $null
try {
    $stateMachine = Start-Process `
        -FilePath "python" `
        -ArgumentList @(
            "$repo\mp257\mission_state_machine.py",
            "--vision-latest", "$repo\tests\missing_vision.json",
            "--uwb-latest", $uwbLatest,
            "--decision-latest", $decision,
            "--period", "0.05",
            "--uwb-max-age", "5.0",
            "--require-flight",
            "--mavlink-udp-port", "5022"
        ) `
        -RedirectStandardOutput $stateLog `
        -PassThru `
        -WindowStyle Hidden

    $heartbeat = Start-Process `
        -FilePath "python" `
        -ArgumentList @("$repo\tools\fake_mavlink_heartbeat.py", "--host", "127.0.0.1", "--port", "5022", "--seconds", "4", "--rate", "10") `
        -PassThru `
        -WindowStyle Hidden

    $uwbWriter = Start-Process `
        -FilePath "python" `
        -ArgumentList @("$repo\tools\write_fake_uwb_latest.py", "--latest", $uwbLatest, "--distance-m", "3.2", "--azimuth-deg", "30", "--seconds", "3", "--rate", "10") `
        -PassThru `
        -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(5)
    $lastState = $null
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $decision) {
            $msg = Get-Content -LiteralPath $decision -Raw | ConvertFrom-Json
            $lastState = $msg.state
            if ($msg.state -eq "UWB_APPROACH") {
                Write-Host "OK local UWB stack reached $($msg.state)"
                Write-Host "OK command mode=$($msg.command.mode) vx=$($msg.command.vx_mps) vy=$($msg.command.vy_mps)"
                return
            }
        }
        Start-Sleep -Milliseconds 100
    }

    Write-Host "--- state log ---"
    if (Test-Path -LiteralPath $stateLog) {
        Get-Content -LiteralPath $stateLog | Select-Object -Last 30
    }
    throw "expected UWB_APPROACH, got $lastState"
}
finally {
    foreach ($proc in @($uwbWriter, $heartbeat, $stateMachine)) {
        if ($proc -and !$proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}
