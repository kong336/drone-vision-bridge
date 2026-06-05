param(
    [string]$Jetson = "root@100.88.97.62",
    [string]$Mp257 = "root@100.88.127.115"
)

$ErrorActionPreference = "Stop"

Write-Host "Preparing Jetson SSH key..."
$pubkey = (ssh $Jetson @"
set -e
mkdir -p /root/.ssh
chmod 700 /root/.ssh
if [ ! -f /root/.ssh/id_ed25519 ]; then
  ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519 -C 'jetson-root-to-mp257' >/dev/null
fi
chmod 600 /root/.ssh/id_ed25519
chmod 644 /root/.ssh/id_ed25519.pub
cat /root/.ssh/id_ed25519.pub
"@ | Select-Object -Last 1).Trim()

if (-not $pubkey.StartsWith("ssh-ed25519 ")) {
    throw "Unexpected Jetson public key output: $pubkey"
}

Write-Host "Installing Jetson public key on MP257..."
$escaped = $pubkey.Replace("'", "'\''")
ssh $Mp257 @"
set -e
mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
grep -qxF '$escaped' /root/.ssh/authorized_keys || printf '%s\n' '$escaped' >> /root/.ssh/authorized_keys
"@

Write-Host "Testing Jetson -> MP257 SSH..."
ssh $Jetson "ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no $Mp257 'hostname; date'"
Write-Host "Jetson can SSH to MP257."
