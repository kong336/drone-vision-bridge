$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$latest = Join-Path $env:TEMP "drone_vision_latest_udp_test.json"
if (Test-Path -LiteralPath $latest) {
    Remove-Item -LiteralPath $latest -Force
}

$receiver = Start-Process `
    -FilePath "python" `
    -ArgumentList @("$repo\mp257\udp_detection_receiver.py", "--host", "127.0.0.1", "--port", "5015", "--latest", $latest) `
    -PassThru `
    -WindowStyle Hidden

try {
    Start-Sleep -Milliseconds 500
    python "$repo\tools\replay_vision_udp.py" --samples "$repo\tests\mission_replay_scenarios.jsonl" --host 127.0.0.1 --port 5015 --interval 0.02
    Start-Sleep -Milliseconds 500
    if (!(Test-Path -LiteralPath $latest)) {
        throw "latest file was not written: $latest"
    }
    $msg = Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json
    if ($msg.status -ne "ok") {
        throw "unexpected status: $($msg.status)"
    }
    if (-not $msg._received) {
        throw "missing _received metadata"
    }
    Write-Host "OK UDP receiver wrote $latest"
    Write-Host "last valid=$($msg.valid) target=$($msg.target.class) received_from=$($msg._received.from)"
}
finally {
    if (!$receiver.HasExited) {
        Stop-Process -Id $receiver.Id -Force
    }
}
