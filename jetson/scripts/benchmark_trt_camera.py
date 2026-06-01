#!/usr/bin/env python3
import argparse
import time

import cv2

from trt_yolo_server import TensorRTEngine, decode, preprocess


def parse_source(value):
    return int(value) if value.isdigit() else value


def main():
    parser = argparse.ArgumentParser(description="Benchmark camera + preprocessing + TensorRT + postprocessing.")
    parser.add_argument("--engine", default="models/snow_king_320_fp16.engine")
    parser.add_argument("--source", default="0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    args = parser.parse_args()

    detector = TensorRTEngine(args.engine)
    _, _, input_h, input_w = detector.input_shape
    if input_h != input_w:
        raise SystemExit(f"Expected square model input, got {detector.input_shape}")

    cap = cv2.VideoCapture(parse_source(args.source), cv2.CAP_V4L2 if args.source.isdigit() else cv2.CAP_ANY)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if args.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    if not cap.isOpened():
        raise SystemExit("Could not open camera")

    # Warmup
    for _ in range(20):
        ok, frame = cap.read()
        if ok:
            inp, scale, pad_x, pad_y = preprocess(frame, input_h)
            output = detector.infer(inp)
            decode(output, frame.shape, scale, pad_x, pad_y, args.conf, args.iou)

    stage = {"capture": 0.0, "preprocess": 0.0, "infer": 0.0, "postprocess": 0.0}
    count = 0
    started = time.time()
    while count < args.frames:
        t0 = time.time()
        ok, frame = cap.read()
        t1 = time.time()
        if not ok or frame is None:
            continue
        inp, scale, pad_x, pad_y = preprocess(frame, input_h)
        t2 = time.time()
        output = detector.infer(inp)
        t3 = time.time()
        decode(output, frame.shape, scale, pad_x, pad_y, args.conf, args.iou)
        t4 = time.time()
        stage["capture"] += t1 - t0
        stage["preprocess"] += t2 - t1
        stage["infer"] += t3 - t2
        stage["postprocess"] += t4 - t3
        count += 1

    elapsed = time.time() - started
    cap.release()
    print(f"frames={count} elapsed={elapsed:.3f}s end_to_end_fps={count / elapsed:.1f}")
    for name, value in stage.items():
        print(f"{name}_ms={(value / count) * 1000:.3f}")


if __name__ == "__main__":
    main()
