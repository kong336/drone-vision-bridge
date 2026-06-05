# Drone Vision Bridge

[![Local stack tests](https://github.com/kong336/drone-vision-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/kong336/drone-vision-bridge/actions/workflows/ci.yml)

Jetson-to-STM32MP257 vision and coarse-position bridge for a drone-mounted manipulator prototype.

This repository contains the small scripts and deployment notes used to connect:

- NVIDIA Jetson Xavier NX for camera capture, TensorRT YOLO inference, Orbbec depth sampling, HTTP preview, and UDP JSON output.
- STM32MP257 running OpenSTLinux for receiving Jetson vision packets, polling fallback HTTP, and parsing ALX-AOA-FIT UWB/AOA UART frames.
- A monitor-only flight/arm controller layer that reads MAVLink heartbeat before any future control work.

Large artifacts are intentionally excluded from git: TensorRT engines, ONNX files, YOLO weights, datasets, videos, logs, and vendor SDK archives.

## Current Data Flow

```text
Camera + Orbbec depth
        |
        v
Jetson trt_yolo_server.py
        | HTTP preview + /latest.json
        | UDP JSON
        v
STM32MP257 receiver scripts
        |
        v
future state machine / flight controller / arm controller
```

The Jetson service sends compact JSON datagrams to the STM32MP257. It also exposes a browser preview and `/latest.json` for debugging.

## Repository Layout

```text
jetson/
  camera_check.py                 camera smoke test
  color_detect.py                 early color-target demo
  mjpeg_server.py                 simple MJPEG preview server
  run_coco_depth_service.sh       foreground Jetson YOLO + depth service
  start_coco_depth_service.sh     background Jetson YOLO + depth service
  scripts/
    trt_yolo_server.py            TensorRT YOLO HTTP/UDP service
    benchmark_trt_camera.py       camera + inference benchmark
    build_trt_yolov8.sh           trtexec build helper
    capture_dataset.py            capture helper for custom training data
  orbbec/
    depth_grid_daemon.cpp         writes depth grid JSON for the vision service
    depth_center_json.cpp         minimal depth smoke test
    install_udev_and_check.sh     Orbbec USB permission setup

mp257/
  udp_detection_receiver.py       listens for Jetson UDP packets
  poll_latest.py                  HTTP polling fallback
  check_vision_receiver.sh        receiver health check
  check_full_stack.sh             one-command Jetson/vision/MAVLink health check
  uwb_aoa_reader.py               ALX-AOA-FIT UART frame parser
  mission_state_machine.py        dry-run mission state machine
  arm_dry_run_monitor.py          dry-run manipulator decision consumer
  preflight_check.py              read-only bench preflight checker
  arm_servo_config.example.json   guarded future servo config template
  flight_link_probe.py            read-only USB serial and MAVLink heartbeat probe

deployment/systemd/
  example services for Jetson and STM32MP257

deployment/
  status_snapshot.ps1             read-only PC snapshot of Tailscale, Jetson, and MP257 links

docs/
  deployment.md                   setup and runbook
  bench_validation.md             offline and board bench validation sequence
  ethernet_link.md                direct Jetson-MP257 wired link
  direct_ethernet_no_gateway.md   direct cable setup that preserves Internet routes
  manipulator_integration.md      dry-run manipulator handoff and next steps
  protocols.md                    JSON and UWB/AOA frame notes
  state_machine.md                monitor-only mission state machine

tools/
  replay_vision_udp.py             replay JSON vision samples over UDP for bench tests
  fake_mavlink_heartbeat.py        fake HEARTBEAT sender for local require-flight tests
  write_fake_uwb_latest.py         fake UWB/AOA latest-file writer for bench tests
  validate_json_file.py            lightweight runtime JSON contract checker

schemas/
  vision_latest.schema.json         Jetson UDP/latest.json contract
  uwb_aoa.schema.json               ALX-AOA-FIT latest-file contract
  mission_decision.schema.json      MP257 state-machine output contract
  arm_action.schema.json            dry-run manipulator action contract

tests/
  mission_replay_scenarios.jsonl   deterministic state-machine replay samples
  stable_grab_vision.jsonl          repeated stable target samples
  test_mission_state_machine.py    offline state-machine assertions
  test_udp_receiver_roundtrip.ps1  local UDP receiver roundtrip test
  test_mavlink_heartbeat_probe.ps1 local MAVLink HEARTBEAT probe test
  test_uwb_aoa_reader.ps1          local UWB/AOA parser and latest-file test
  test_local_uwb_stack.ps1         fake UWB + fake MAVLink -> state-machine simulation
  test_local_full_stack.ps1         local UDP -> state -> arm dry-run simulation
  run_local_tests.ps1               one-command local test suite
```

## Quick Start

On the Jetson:

```bash
cd /home/nvidia/vision_starter
UDP_HOST=MP257_IP_OR_HOSTNAME ./start_coco_depth_service.sh
```

On the STM32MP257:

```bash
python3 /root/vision_comm/udp_detection_receiver.py --port 5005
```

Debug from another machine:

```text
http://JETSON_IP:8090/
http://JETSON_IP:8090/latest.json
```

Current tested Jetson endpoint:

```text
http://100.88.97.62:8090/
```

Current deployed wrench model:

```text
/home/nvidia/vision_starter/models/wrench_public_neg_320_fp16.engine
```

## Communication Choice

For onboard Jetson-to-STM32MP257 vision packets, a direct Ethernet link is the best practical real-time link: it is local, low latency, high bandwidth, and independent of Wi-Fi or Tailscale. Use Tailscale for remote SSH and log inspection, not for flight-critical control.

For hard real-time actuator and flight stabilization, keep the flight controller in charge and use appropriate control links such as MAVLink over UART, CAN, PWM, or the flight controller's native buses.

## Monitor-Only State Machine

The MP257 state machine is intentionally dry-run by default:

```bash
python3 mp257/mission_state_machine.py --once
```

With a future MAVLink heartbeat source:

```bash
python3 mp257/mission_state_machine.py --mavlink-serial auto --mavlink-baud 115200 --require-flight
```

It prints target state and proposed dry-run commands, but does not arm the aircraft or send movement commands.
