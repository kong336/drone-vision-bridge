param(
    [string]$Jetson = "root@100.88.97.62",
    [string]$Mp257 = "root@100.88.127.115"
)

$ErrorActionPreference = "Continue"

$tailscale = "C:\Program Files\Tailscale\tailscale.exe"
if (Test-Path -LiteralPath $tailscale) {
    & $tailscale status
} else {
    Write-Warning "tailscale.exe not found at $tailscale"
}

Write-Host "--- PC -> Jetson SSH ---"
ssh -o BatchMode=yes -o ConnectTimeout=8 $Jetson "hostname; date"

Write-Host "--- PC -> MP257 SSH ---"
ssh -o BatchMode=yes -o ConnectTimeout=8 $Mp257 "hostname; date"

Write-Host "--- Jetson -> MP257 SSH ---"
ssh -o BatchMode=yes -o ConnectTimeout=8 $Jetson "ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no $Mp257 'hostname; date'"
