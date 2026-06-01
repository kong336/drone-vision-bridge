#!/usr/bin/env python3
import argparse
import json
import time
import urllib.request
from pathlib import Path


def summarize(msg):
    target = msg.get('target') or {}
    offset = target.get('offset') or {}
    if target:
        return 'status={status} valid={valid} conf={conf} dx={dx} dy={dy} fps={fps}'.format(
            status=msg.get('status'), valid=msg.get('valid'), conf=target.get('conf'),
            dx=offset.get('dx'), dy=offset.get('dy'), fps=msg.get('fps'))
    return 'status={status} valid={valid} detections={n}'.format(
        status=msg.get('status'), valid=msg.get('valid'), n=len(msg.get('detections') or []))


def main():
    parser = argparse.ArgumentParser(description='Poll Jetson /latest.json over HTTP.')
    parser.add_argument('--url', default='http://192.168.1.45:8090/latest.json')
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--latest', default='/root/vision_comm/latest_http.json')
    parser.add_argument('--raw', action='store_true')
    args = parser.parse_args()
    latest_path = Path(args.latest)
    print(f'polling {args.url}', flush=True)
    while True:
        try:
            with urllib.request.urlopen(args.url, timeout=3) as response:
                msg = json.loads(response.read().decode('utf-8'))
            latest_path.write_text(json.dumps(msg, ensure_ascii=False, separators=(',', ':')) + '\n')
            print(json.dumps(msg, ensure_ascii=False) if args.raw else time.strftime('%H:%M:%S') + ' ' + summarize(msg), flush=True)
        except Exception as exc:
            print(time.strftime('%H:%M:%S'), 'poll_error', repr(exc), flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
