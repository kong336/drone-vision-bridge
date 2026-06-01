# Deployment Notes

## Jetson

Expected baseline:

- Ubuntu 20.04 on Jetson Xavier NX
- CUDA and TensorRT installed
- Python 3 with OpenCV, NumPy, and TensorRT Python bindings
- Camera visible as `/dev/video*`
- TensorRT engine already built under `models/`
- Optional Orbbec SDK installed for depth

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

Start the live COCO + depth service:

```bash
cd /home/nvidia/vision_starter
UDP_HOST=192.168.1.175 UDP_PORT=5005 ./start_coco_depth_service.sh
```

Useful overrides:

```bash
UDP_HOST=10.10.10.2
UDP_PORT=5005
UDP_RATE=20
ENGINE=models/yolov8n_320_fp16.engine
DEPTH_JSON=/tmp/orbbec_depth_grid.json
```

## STM32MP257

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

## UWB/AOA

Read ALX-AOA-FIT frames from a UART:

```bash
python3 /root/vision_comm/uwb_aoa_reader.py --serial /dev/ttySTM1 --baud 115200
```

The script prints JSON lines containing `distance_m`, `azimuth_deg`, and `elevation_deg`.

