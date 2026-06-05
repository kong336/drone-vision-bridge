$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

function Test-HeartbeatProbe {
    param(
        [int]$Port,
        [switch]$Armed,
        [bool]$ExpectedArmed
    )

    $args = @("$repo\tools\fake_mavlink_heartbeat.py", "--host", "127.0.0.1", "--port", "$Port", "--seconds", "2", "--rate", "10")
    if ($Armed) {
        $args += "--armed"
    }

    $sender = Start-Process `
        -FilePath "python" `
        -ArgumentList $args `
        -PassThru `
        -WindowStyle Hidden

    try {
        Start-Sleep -Milliseconds 200
        $report = python "$repo\mp257\flight_link_probe.py" --udp-port $Port --seconds 2 | ConvertFrom-Json
        if (-not $report.mavlink.ok) {
            throw "MAVLink probe did not see heartbeat on UDP port $Port"
        }
        if ([bool]$report.mavlink.armed -ne $ExpectedArmed) {
            throw "Expected armed=$ExpectedArmed on port $Port, got $($report.mavlink.armed)"
        }
        Write-Host "OK heartbeat probe port=$Port armed=$($report.mavlink.armed)"
    }
    finally {
        if (!$sender.HasExited) {
            Stop-Process -Id $sender.Id -Force
        }
    }
}

Test-HeartbeatProbe -Port 5018 -ExpectedArmed $false
Test-HeartbeatProbe -Port 5019 -Armed -ExpectedArmed $true

$autoReport = python "$repo\mp257\flight_link_probe.py" --serial auto --seconds 0.1 | ConvertFrom-Json
if ($autoReport.mavlink.checked -ne $true) {
    throw "Expected auto serial probe to run a checked probe"
}
if ($autoReport.mavlink.ok -eq $true) {
    Write-Host "OK heartbeat probe serial=auto armed=$($autoReport.mavlink.armed)"
} else {
    Write-Host "OK heartbeat probe serial=auto no by-id flight controller found"
}
