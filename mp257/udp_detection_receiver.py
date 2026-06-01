#!/usr/bin/env python3
import argparse
import json
import socket
import time
from pathlib import Path


def summarize(msg):
    target = msg.get('target') or {}
    offset = target.get('offset') or {}
    depth = msg.get('depth') or {}
    status = msg.get('status')
    valid = msg.get('valid')
    dx = offset.get('dx')
    dy = offset.get('dy')
    distance = target.get('distance_m', msg.get('distance_m'))
    depth_ok = depth.get('ok')
    cls = target.get('class')
    conf = target.get('conf')
    dets = len(msg.get('detections') or [])
    return f"status={status} valid={valid} class={cls} conf={conf} distance_m={distance} dx={dx} dy={dy} detections={dets} depth_ok={depth_ok}"


def main():
    parser = argparse.ArgumentParser(description='Listen for Jetson vision UDP JSON.')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5005)
    parser.add_argument('--latest', default='/root/vision_comm/latest_udp.json')
    parser.add_argument('--raw', action='store_true')
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    latest_path = Path(args.latest)
    print(f'listening udp://{args.host}:{args.port}', flush=True)
    while True:
        data, addr = sock.recvfrom(65535)
        text = data.decode('utf-8', 'replace')
        try:
            msg = json.loads(text)
            msg['_received'] = {'from': addr[0], 'port': addr[1], 'time': time.time()}
            latest_path.write_text(json.dumps(msg, ensure_ascii=False, separators=(',', ':')) + '\n')
            if args.raw:
                print(json.dumps(msg, ensure_ascii=False), flush=True)
            else:
                print(time.strftime('%H:%M:%S'), addr[0], summarize(msg), flush=True)
        except Exception as exc:
            print(time.strftime('%H:%M:%S'), addr[0], 'bad_packet', repr(exc), text[:200], flush=True)


if __name__ == '__main__':
    main()
