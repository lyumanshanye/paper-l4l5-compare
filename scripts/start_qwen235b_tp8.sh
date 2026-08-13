#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="/inspire/hdd2/project/special-project-1/public/yelv/models/Qwen/Qwen3-235B-A22B-Instruct-2507"
LOG_DIR="/inspire/hdd2/project/special-project-1/public/yelv/paper/paper30_dsv4_compare/qwen_service"
FASTSAFETENSORS_WHEEL="${LOG_DIR}/fastsafetensors-0.3.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PORT=30000

mkdir -p "${LOG_DIR}"

if ! python3 -c "import fastsafetensors" >/dev/null 2>&1; then
  python3 -m pip install --no-index "${FASTSAFETENSORS_WHEEL}"
fi

exec sglang serve \
  --model-path "${MODEL_PATH}" \
  --served-model-name qwen3-235b-a22b \
  --trust-remote-code \
  --load-format fastsafetensors \
  --model-loader-extra-config '{"enable_gds": false}' \
  --tp-size 8 \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --mem-fraction-static 0.90 \
  --chunked-prefill-size 8192 \
  --max-prefill-tokens 16384 \
  --skip-server-warmup \
  > "${LOG_DIR}/server.log" 2>&1
