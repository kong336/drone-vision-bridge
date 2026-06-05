param(
    [string]$Jetson = "root@100.88.97.62",
    [string]$UdpHost = "100.88.127.115",
    [string]$Engine = "models/wrench_public_neg_320_fp16.engine",
    [string]$Label = "wrench",
    [double]$Conf = 0.45
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

Write-Host "Copying Jetson scripts..."
ssh $Jetson "mkdir -p /home/nvidia/vision_starter/scripts /home/nvidia/vision_starter/models"
scp "$repo\jetson\run_coco_depth_service.sh" "${Jetson}:/home/nvidia/vision_starter/run_coco_depth_service.sh"
scp "$repo\jetson\start_coco_depth_service.sh" "${Jetson}:/home/nvidia/vision_starter/start_coco_depth_service.sh"
scp "$repo\jetson\check_vision_stack.sh" "${Jetson}:/home/nvidia/vision_starter/check_vision_stack.sh"
scp "$repo\jetson\scripts\trt_yolo_server.py" "${Jetson}:/home/nvidia/vision_starter/scripts/trt_yolo_server.py"
scp "$repo\jetson\scripts\build_trt_yolov8.sh" "${Jetson}:/home/nvidia/vision_starter/scripts/build_trt_yolov8.sh"
ssh $Jetson "chmod +x /home/nvidia/vision_starter/*.sh /home/nvidia/vision_starter/scripts/*.sh"

$confText = $Conf.ToString("0.00", [Globalization.CultureInfo]::InvariantCulture)
Write-Host "Writing Jetson service override..."
ssh $Jetson @"
set -e
mkdir -p /etc/systemd/system/jetson-vision.service.d
cat >/etc/systemd/system/jetson-vision.service.d/10-local.conf <<'EOF'
[Service]
Environment=UDP_HOST=$UdpHost
Environment=UDP_PORT=5005
Environment=UDP_RATE=20
Environment=ENGINE=$Engine
Environment=LABEL=$Label
Environment=CONF=$confText
EOF
systemctl daemon-reload
systemctl disable --now vision-coco-depth.service 2>/dev/null || true
systemctl enable --now jetson-vision.service
systemctl restart jetson-vision.service
sleep 8
/home/nvidia/vision_starter/check_vision_stack.sh
"@

Write-Host "Jetson stack deploy complete."
Write-Host "Preview: http://100.88.97.62:8090/"
