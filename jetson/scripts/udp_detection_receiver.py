#!/usr/bin/env python3
import argparse
import json
import socket


def main():
    parser = argparse.ArgumentParser(description="Receive Jetson YOLO UDP JSON messages.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"Listening on udp://{args.host}:{args.port}", flush=True)
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            message = json.loads(data.decode("utf-8"))
        except Exception as exc:
            print(f"{addr} invalid payload: {exc}: {data!r}", flush=True)
            continue
        target = message.get("target")
        if target:
            print(
                f"{addr} {target.get('class')} conf={target.get('conf')} "
                f"dx={target.get('offset', {}).get('dx')} dy={target.get('offset', {}).get('dy')}",
                flush=True,
            )
        else:
            print(f"{addr} no target status={message.get('status')}", flush=True)


if __name__ == "__main__":
    main()
