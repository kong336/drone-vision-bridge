# Deployment Notes

## Jetson

Expected baseline:

- Jetson Xavier NX
- CUDA and TensorRT installed
- Python 3 with OpenCV, NumPy, and TensorRT Python bindings
- Camera visible as `/dev/video*`
- TensorRT engine already built under `models/`
- Optional Orbbec SDK installed for depth

Two Jetson baselines have been used:

```text
JetPack 5 path: Ubuntu 20.04 / L4T 35.x / CUDA 11.4 / TensorRT 8.x
JetPack 4 path: Ubuntu 18.04 / L4T 32.4.4 / CUDA 10.2 / TensorRT 7.1.3
```

The version difference is material. Treat `.onnx` as the portable model handoff
and rebuild the `.engine` on the target Jetson. Do not assume a TensorRT 8
engine from the JetPack 5 board will deserialize correctly on the JetPack 4
board. Use a clear suffix such as `trt7_fp16.engine` for JetPack 4 builds.

Run a camera smoke test:

```bash
cd /home/nvidia/vision_starter
python3 camera_check.py --source 0 --frames 120
```

Build a TensorRT engine from an ONNX model:

```bash
cd /home/nvidia/vision_starter
scripts/build_trt_yolov8.sh models/yolov8n_320.onnx models/yolov8n_320_fp16.engine
```

Start the live YOLO + depth service:

```bash
cd /home/nvidia/vision_starter
UDP_HOST=MP257_IP_OR_HOSTNAME UDP_PORT=5005 ./start_coco_depth_service.sh
```

Useful overrides:

```bash
UDP_HOST=100.x.y.z
UDP_PORT=5005
UDP_RATE=20
ENGINE=models/yolov8n_320_fp16.engine
LABEL=coco
CONF=0.15
DEPTH_JSON=/tmp/orbbec_depth_grid.json
```

For the current wrench detector:

```bash
UDP_HOST=100.88.127.115
UDP_PORT=5005
UDP_RATE=20
ENGINE=models/wrench_public_neg_320_fp16.engine
LABEL=wrench
CONF=0.45
```

For the migrated JetPack 4 board at `192.168.1.80`, the current observed
service uses the June 26 combined wrench model and Orbbec RGB/depth path:

```bash
cd /home/nvidia/vision_starter
nohup python3 scripts/trt_yolo_server.py \
  --engine models/wrench_combined_20260626_320_trt7_fp16.engine \
  --source /dev/video1 \
  --width 640 \
  --height 480 \
  --camera-fps 30 \
  --fourcc MJPG \
  --infer-fps 30 \
  --display-fps 20 \
  --capture-thread \
  --label wrench \
  --conf 0.25 \
  --iou 0.45 \
  --max-detections 1 \
  --depth-json /tmp/orbbec_depth_grid.json \
  --depth-max-age 1.0 \
  --camera-hfov-deg 67 \
  --camera-vfov-deg 52 \
  --host 0.0.0.0 \
  --port 8090 \
  > outputs/trt_yolo_server.log 2>&1 < /dev/null &
```

Check it from the PC:

```text
http://192.168.1.80:8090/
http://192.168.1.80:8090/latest.json
```

The useful training/export chain for the current wrench detector is:

```text
train YOLO with public wrench positives + local wrench captures + local negative/background images
export 320 input ONNX
copy ONNX to the Jetson
build FP16 TensorRT engine on the same Jetson/runtime that will run it
serve one best wrench detection with Orbbec depth fused into latest.json
```

Keep these artifacts when cleaning up:

```text
best.pt
best.onnx or wrench_combined_20260626_320.onnx
dataset YAML and train/val split
label conversion/capture helpers
target-board engine, for example wrench_combined_20260626_320_trt7_fp16.engine
```

Temporary browser caches, raw logs, generated preview images, and failed
throwaway engines can be left out of git.

Use the direct Ethernet address for onboard flight tests. Use the MP257 Tailscale IP or MagicDNS name for remote debugging when the boards are not on the same LAN.

## STM32MP257

From the Windows PC, check Tailscale/SSH links:

```powershell
cd C:\Users\allen\drone-vision-bridge
.\deployment\check_tailscale_links.ps1
```

Deploy the Jetson scripts and current service override:

```powershell
.\deployment\deploy_jetson_stack.ps1
```

Install the Jetson root SSH key onto the MP257 so the two boards can SSH directly over Tailscale or a routed direct link:

```powershell
.\deployment\setup_jetson_to_mp257_ssh.ps1
```

Deploy the MP257 receiver/state-machine scripts:

```powershell
.\deployment\deploy_mp257_stack.ps1
```

After checking configuration, enable the services:

```powershell
.\deployment\deploy_mp257_stack.ps1 -EnableServices
```

The UWB/AOA reader service is installed but not enabled by default. After confirming the UART path, enable it explicitly:

```powershell
.\deployment\deploy_mp257_stack.ps1 -EnableServices -EnableUwbService
```

Receive Jetson UDP packets:

```bash
python3 /root/vision_comm/udp_detection_receiver.py --port 5005
```

Poll Jetson HTTP as a fallback:

```bash
python3 /root/vision_comm/poll_latest.py --url http://192.168.1.45:8090/latest.json
```

Check receiver state:

```bash
sh /root/vision_comm/check_vision_receiver.sh
```

Check the full running stack:

```bash
sh /root/vision_comm/check_full_stack.sh
```

Run a read-only preflight check without changing services or outputs:

```bash
python3 /root/vision_comm/preflight_check.py \
  --root /root/vision_comm \
  --jetson-health-url http://100.88.97.62:8090/healthz
```

After the MP257 is back online, the Windows bench runbook is:

```powershell
cd C:\Users\allen\drone-vision-bridge
.\deployment\bench_validate_after_mp257_online.ps1
```

Probe the flight controller without sending any command:

```bash
python3 /root/vision_comm/flight_link_probe.py --serial auto --baud 115200
```

Run the dry-run state machine with a required MAVLink heartbeat:

```bash
python3 /root/vision_comm/mission_state_machine.py \
  --vision-latest /root/vision_comm/latest_udp.json \
  --uwb-latest /root/vision_comm/latest_uwb.json \
  --mavlink-serial auto \
  --mavlink-baud 115200 \
  --require-flight
```

`auto` looks for stable `/dev/serial/by-id/*ArduPilot*` or `/dev/serial/by-id/*PX4*` links. If no flight controller is found, the state machine stays in `WAIT_FLIGHT_SAFE` when `--require-flight` is enabled.

## UWB/AOA

Read ALX-AOA-FIT frames from a UART:

```bash
python3 /root/vision_comm/uwb_aoa_reader.py --serial /dev/ttySTM1 --baud 115200
```

The script prints JSON lines containing `distance_m`, `azimuth_deg`, and `elevation_deg`.

For state-machine coarse positioning, write a latest file:

```bash
python3 /root/vision_comm/uwb_aoa_reader.py \
  --serial /dev/ttySTM1 \
  --baud 115200 \
  --latest /root/vision_comm/latest_uwb.json
```

The optional `mp257-uwb-aoa-reader.service` is installed by the deploy script but not enabled by default. Enable it only after confirming the correct UART path, or deploy with `-EnableUwbService`.
