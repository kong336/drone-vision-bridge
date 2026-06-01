#!/bin/sh
set -eu

SDK_ROOT="/home/nvidia/orbbec_sdk/v1/OrbbecSDK_v1.10.35"
PROBE="/home/nvidia/orbbec_sdk/depth_center_json"

if [ "$(id -u)" != "0" ]; then
  echo "Run with sudo on the Jetson:"
  echo "  sudo sh /home/nvidia/orbbec_sdk/install_udev_and_check.sh"
  exit 1
fi

cp "$SDK_ROOT/Script/99-obsensor-libusb.rules" /etc/udev/rules.d/99-obsensor-libusb.rules
udevadm control --reload-rules
udevadm trigger

echo "--- Orbbec USB devices ---"
for d in /sys/bus/usb/devices/*; do
  if [ -f "$d/idVendor" ] && [ "$(cat "$d/idVendor")" = "2bc5" ]; then
    bus="$(cat "$d/busnum")"
    dev="$(cat "$d/devnum")"
    printf '%s %s speed=%sM bus=%s dev=%s\n' \
      "$(cat "$d/idProduct")" \
      "$(cat "$d/product" 2>/dev/null || true)" \
      "$(cat "$d/speed")" "$bus" "$dev"
    ls -l "/dev/bus/usb/$(printf '%03d' "$bus")/$(printf '%03d' "$dev")"
  fi
done

echo "--- Depth probe ---"
LD_LIBRARY_PATH="$SDK_ROOT/SDK/lib:${LD_LIBRARY_PATH:-}" "$PROBE" 20
