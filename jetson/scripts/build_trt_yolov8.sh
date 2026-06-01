#!/usr/bin/env bash
set -euo pipefail

ONNX_PATH="${1:-models/best_320.onnx}"
ENGINE_PATH="${2:-models/best_320_fp16.engine}"
WORKSPACE="${WORKSPACE:-1024}"

if [[ ! -f "$ONNX_PATH" ]]; then
  echo "ONNX file not found: $ONNX_PATH" >&2
  exit 1
fi

/usr/src/tensorrt/bin/trtexec \
  --onnx="$ONNX_PATH" \
  --saveEngine="$ENGINE_PATH" \
  --fp16 \
  --workspace="$WORKSPACE" \
  --buildOnly

ls -lh "$ENGINE_PATH"
