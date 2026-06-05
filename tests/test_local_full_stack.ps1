$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$latest = Join-Path $env:TEMP "drone_vision_full_stack_latest_udp.json"
$decision = Join-Path $env:TEMP "drone_vision_full_stack_latest_decision.json"
$stateLog = Join-Path $env:TEMP "drone_vision_full_stack_state.log"
$enableFile = Join-Path $env:TEMP "drone_vision_ENABLE_ARM_DRY_RUN"

foreach ($path in @($latest, $decision, $stateLog, $enableFile)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$receiver = $null
$stateMachine = $null
$heartbeat = $null
try {
    $receiver = Start-Process `
        -FilePath "python" `
        -ArgumentList @("$repo\mp257\udp_detection_receiver.py", "--host", "127.0.0.1", "--port", "5016", "--latest", $latest) `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Milliseconds 500

    $stateMachine = Start-Process `
        -FilePath "python" `
        -ArgumentList @("$repo\mp257\mission_state_machine.py", "--vision-latest", $latest, "--decision-latest", $decision, "--period", "0.05", "--vision-max-age", "5.0", "--require-flight", "--mavlink-udp-port", "5017") `
        -RedirectStandardOutput $stateLog `
        -PassThru `
        -WindowStyle Hidden

    $heartbeat = Start-Process `
        -FilePath "python" `
        -ArgumentList @("$repo\tools\fake_mavlink_heartbeat.py", "--host", "127.0.0.1", "--port", "5017", "--seconds", "4", "--rate", "10") `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Milliseconds 500

    python "$repo\tools\replay_vision_udp.py" --samples "$repo\tests\stable_grab_vision.jsonl" --host 127.0.0.1 --port 5016 --interval 0.08
    Start-Sleep -Seconds 1

    if (!(Test-Path -LiteralPath $decision)) {
        throw "decision file was not written: $decision"
    }

    $msg = Get-Content -LiteralPath $decision -Raw | ConvertFrom-Json
    if ($msg.state -ne "GRAB_DRY_RUN") {
        Write-Host "--- state log ---"
        if (Test-Path -LiteralPath $stateLog) {
            Get-Content -LiteralPath $stateLog | Select-Object -Last 20
        }
        throw "expected GRAB_DRY_RUN, got $($msg.state)"
    }

    $blockedOutput = python "$repo\mp257\arm_dry_run_monitor.py" --decision-latest $decision --enable-file $enableFile --once | ConvertFrom-Json
    if ($blockedOutput.arm_dry_run.mode -ne "blocked_requires_enable_file") {
        throw "expected blocked_requires_enable_file, got $($blockedOutput.arm_dry_run.mode)"
    }

    New-Item -ItemType File -Path $enableFile | Out-Null
    $enabledOutput = python "$repo\mp257\arm_dry_run_monitor.py" --decision-latest $decision --enable-file $enableFile --once | ConvertFrom-Json
    if ($enabledOutput.arm_dry_run.mode -ne "would_close_gripper") {
        throw "expected would_close_gripper, got $($enabledOutput.arm_dry_run.mode)"
    }

    Write-Host "OK local full stack simulation reached $($msg.state)"
    Write-Host "OK arm dry-run guard mode=$($blockedOutput.arm_dry_run.mode)"
    Write-Host "OK arm dry-run enabled mode=$($enabledOutput.arm_dry_run.mode)"
}
finally {
    foreach ($proc in @($heartbeat, $stateMachine, $receiver)) {
        if ($proc -and !$proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}
