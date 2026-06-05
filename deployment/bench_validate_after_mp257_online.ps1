param(
    [string]$Jetson = "root@100.88.97.62",
    [string]$Mp257 = "root@100.88.127.115",
    [switch]$SkipLocalTests,
    [switch]$EnableUwbService
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

if (-not $SkipLocalTests) {
    Write-Host "== Local safety tests =="
    powershell -ExecutionPolicy Bypass -File "$repo\tests\run_local_tests.ps1"
}

Write-Host "== Read-only status snapshot =="
& "$repo\deployment\status_snapshot.ps1" -Jetson $Jetson -Mp257 $Mp257

Write-Host "== Tailscale and SSH links =="
& "$repo\deployment\check_tailscale_links.ps1" -Jetson $Jetson -Mp257 $Mp257

Write-Host "== Jetson vision stack =="
ssh $Jetson "/home/nvidia/vision_starter/check_vision_stack.sh"

Write-Host "== Install Jetson -> MP257 SSH key =="
& "$repo\deployment\setup_jetson_to_mp257_ssh.ps1" -Jetson $Jetson -Mp257 $Mp257

Write-Host "== Deploy MP257 stack =="
if ($EnableUwbService) {
    & "$repo\deployment\deploy_mp257_stack.ps1" -Mp257 $Mp257 -EnableServices -EnableUwbService
} else {
    & "$repo\deployment\deploy_mp257_stack.ps1" -Mp257 $Mp257 -EnableServices
}

Write-Host "== MP257 stack health =="
ssh $Mp257 "JETSON_HEALTH_URL=http://100.88.97.62:8090/healthz /root/vision_comm/check_full_stack.sh || true"

Write-Host "== Service logs =="
ssh $Mp257 "systemctl --no-pager --plain status vision-udp-receiver.service mp257-mission-state-machine.service mp257-arm-dry-run.service mp257-uwb-aoa-reader.service | sed -n '1,200p'"

Write-Host "Bench validation script finished. Review FAIL lines before any physical test."
