# Direct Ethernet Link

A direct wired link between Jetson and STM32MP257 is the preferred onboard link for vision telemetry.

Recommended static addresses:

```text
Jetson eth0:      10.10.10.1/24
STM32MP257 end0:  10.10.10.2/24
```

Then run Jetson UDP output toward the MP257:

```bash
UDP_HOST=10.10.10.2 UDP_PORT=5005 ./start_coco_depth_service.sh
```

And poll Jetson from the MP257 with:

```bash
python3 poll_latest.py --url http://10.10.10.1:8090/latest.json
```

## Why Ethernet

Ethernet is better than Wi-Fi or Tailscale for onboard Jetson-to-MP257 data:

- local link, no router or internet dependency
- lower and more predictable latency
- enough bandwidth for JSON, preview, logs, and future debug traffic
- easy to isolate from remote SSH/VPN traffic

It is still not a replacement for the flight controller. The flight controller should keep attitude stabilization and failsafe behavior local.

## Tailscale Role

Use Tailscale for:

- SSH into Jetson and MP257 from outside the local Wi-Fi
- checking logs
- changing configuration before tests

Do not make the drone depend on Tailscale to stay stable in flight.

