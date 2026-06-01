# Direct Ethernet Without Losing Internet

Use this when the STM32MP257 still needs Internet/Tailscale access, but Jetson-to-MP257 vision packets should later move to a direct cable.

## Current Safe Mode

Keep the current Internet path active:

```text
MP257 end0: DHCP Internet, Tailscale online
Jetson wlan0: Wi-Fi Internet, Tailscale online
Jetson eth0: reserved for direct cable
```

Do not set a default gateway on the direct-link addresses.

## Temporary Direct-Link Addresses

On the Jetson:

```bash
cd /home/nvidia/vision_starter
sudo IFACE=eth0 ADDR=10.10.10.1/24 ./setup_direct_ethernet.sh
```

On the MP257:

```bash
cd /root/vision_comm
IFACE=end0 ADDR=10.10.10.2/24 ./setup_direct_ethernet.sh
```

Then test:

```bash
ping 10.10.10.1
curl http://10.10.10.1:8090/healthz
```

After the direct cable is stable, switch the Jetson vision service override from the MP257 Tailscale IP to:

```text
UDP_HOST=10.10.10.2
```

## Important

On the inspected MP257, `end0` is currently the Internet uplink. Replacing its DHCP setup with a static-only direct link would disconnect remote access. Add the direct-link address only when you are physically ready, and do not add a gateway for `10.10.10.0/24`.
