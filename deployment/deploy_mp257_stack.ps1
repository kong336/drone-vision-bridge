param(
    [string]$Mp257 = "root@100.88.127.115",
    [switch]$EnableServices,
    [switch]$EnableUwbService
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

Write-Host "Copying MP257 scripts..."
ssh $Mp257 "mkdir -p /root/vision_comm"
@(Get-ChildItem -Path "$repo\mp257\*.py" -File) + @(Get-ChildItem -Path "$repo\mp257\*.sh" -File) | ForEach-Object {
    scp $_.FullName "${Mp257}:/root/vision_comm/"
}
if (Test-Path -LiteralPath "$repo\mp257\arm_servo_config.example.json") {
    scp "$repo\mp257\arm_servo_config.example.json" "${Mp257}:/root/vision_comm/"
}
if (Test-Path -LiteralPath "$repo\tools\validate_json_file.py") {
    scp "$repo\tools\validate_json_file.py" "${Mp257}:/root/vision_comm/"
}
if (Test-Path -LiteralPath "$repo\tools\write_fake_uwb_latest.py") {
    scp "$repo\tools\write_fake_uwb_latest.py" "${Mp257}:/root/vision_comm/"
}
if (Test-Path -LiteralPath "$repo\schemas") {
    ssh $Mp257 "mkdir -p /root/vision_comm/schemas"
    Get-ChildItem -Path "$repo\schemas\*.json" -File | ForEach-Object {
        scp $_.FullName "${Mp257}:/root/vision_comm/schemas/"
    }
}
ssh $Mp257 "chmod +x /root/vision_comm/*.py /root/vision_comm/*.sh"

Write-Host "Copying systemd units..."
scp "$repo\deployment\systemd\mp257-vision-receiver.service" "${Mp257}:/etc/systemd/system/vision-udp-receiver.service"
scp "$repo\deployment\systemd\mp257-mission-state-machine.service" "${Mp257}:/etc/systemd/system/mp257-mission-state-machine.service"
scp "$repo\deployment\systemd\mp257-arm-dry-run.service" "${Mp257}:/etc/systemd/system/mp257-arm-dry-run.service"
scp "$repo\deployment\systemd\mp257-uwb-aoa-reader.service" "${Mp257}:/etc/systemd/system/mp257-uwb-aoa-reader.service"
ssh $Mp257 "systemctl daemon-reload"

if ($EnableServices) {
    Write-Host "Enabling and starting MP257 services..."
    ssh $Mp257 "systemctl enable --now vision-udp-receiver.service mp257-mission-state-machine.service mp257-arm-dry-run.service"
    if ($EnableUwbService) {
        Write-Host "Enabling optional UWB/AOA reader service..."
        ssh $Mp257 "systemctl enable --now mp257-uwb-aoa-reader.service"
    } else {
        Write-Host "Optional UWB/AOA reader service installed but not enabled. Re-run with -EnableUwbService after confirming UWB_SERIAL."
    }
} else {
    Write-Host "Services installed but not enabled. Re-run with -EnableServices after checking config."
}

Write-Host "MP257 stack deploy complete."
