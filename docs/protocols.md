# Protocol Notes

## Jetson Vision UDP

The Jetson sends one JSON object per UDP datagram. Typical fields:

```json
{
  "valid": true,
  "status": "ok",
  "source": "0",
  "timestamp": 1780117200.0,
  "image": {"w": 640, "h": 480, "center_x": 320, "center_y": 240},
  "fps": 38.0,
  "target": {
    "class": "person",
    "conf": 0.82,
    "box": {"x": 250, "y": 180, "w": 120, "h": 90},
    "center": {"x": 310, "y": 225},
    "offset": {"dx": -10, "dy": -15},
    "distance_m": 1.37
  },
  "detections": []
}
```

`dx` and `dy` are pixel offsets from the image center. The MP257 can use them for slow visual alignment after coarse positioning.

## ALX-AOA-FIT UART

Serial settings:

```text
115200 baud, 8 data bits, 1 stop bit, no parity, no flow control
```

Location frame command: `0x2001`.

Important fields:

```text
MessageHeader: FF FF FF FF
Distance:      uint32, cm
Azimuth:       int16, degrees
Elevation:     int16, degrees
XorByte:       XOR checksum over previous bytes
```

The parser in `mp257/uwb_aoa_reader.py` emits JSON:

```json
{
  "ok": true,
  "cmd": "location",
  "distance_m": 0.98,
  "azimuth_deg": -39,
  "elevation_deg": 13
}
```

