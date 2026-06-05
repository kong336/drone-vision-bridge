param(
    [string]$Jetson = "root@100.88.97.62",
    [string]$JetsonHttp = "http://100.88.97.62:8090",
    [string]$Mp257 = "root@100.88.127.115"
)

$ErrorActionPreference = "Continue"

function Invoke-SshLine {
    param(
        [string]$Target,
        [string]$Command
    )
    $output = ssh -o BatchMode=yes -o ConnectTimeout=6 $Target $Command 2>&1
    if ($LASTEXITCODE -eq 0) {
        $output
    } else {
        Write-Host "[FAIL] ssh $Target"
        $output | ForEach-Object { Write-Host "  $_" }
    }
}

Write-Host "== Tailscale =="
$tailscale = "C:\Program Files\Tailscale\tailscale.exe"
if (Test-Path -LiteralPath $tailscale) {
    & $tailscale status
} else {
    Write-Warning "tailscale.exe not found at $tailscale"
}

Write-Host ""
Write-Host "== Jetson SSH =="
Invoke-SshLine -Target $Jetson -Command "hostname; systemctl is-active jetson-vision.service; systemctl is-enabled vision-coco-depth.service || true"

Write-Host ""
Write-Host "== Jetson HTTP latest =="
try {
    $latest = Invoke-RestMethod -Uri "$JetsonHttp/latest.json" -TimeoutSec 5
    $target = $latest.target
    [pscustomobject]@{
        status = $latest.status
        valid = $latest.valid
        fps = $latest.fps
        target_class = if ($target) { $target.class } else { $null }
        conf = if ($target) { $target.conf } else { $null }
        distance_m = if ($target -and $target.distance_m) { $target.distance_m } else { $latest.distance_m }
        preview = "$JetsonHttp/"
    } | Format-List
} catch {
    Write-Warning "Jetson latest.json failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "== MP257 SSH =="
Invoke-SshLine -Target $Mp257 -Command "hostname; date; test -x /root/vision_comm/preflight_check.py && echo preflight_check_present || echo preflight_check_missing"

Write-Host ""
Write-Host "== Jetson -> MP257 SSH =="
Invoke-SshLine -Target $Jetson -Command "ssh -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=no $Mp257 'hostname; date'"

Write-Host ""
Write-Host "Snapshot finished."
