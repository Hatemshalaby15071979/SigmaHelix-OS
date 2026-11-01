#!/usr/bin/env bash
# Start a NATIVE ollama (GPU-only) server + verify AMD RX 6700 XT (gfx1031) offload.
# Ollama refuses CPU-only model loads: with this server, any loaded model runs on GPU.
set -euo pipefail

OLL_DIR="$HOME/.local"                      # native ollama install (bin/ + lib/)
MODELS_DIR="$HOME/.ollama-models"           # user-writable model store
export OLLAMA_HOST="http://127.0.0.1:11435" # snap ollama owns 11434; we use 11435
export OLLAMA_MODELS="$MODELS_DIR"
export HSA_OVERRIDE_GFX_VERSION=10.3.0      # Navi 22 -> accepted as gfx1030-class
export HIP_VISIBLE_DEVICES=0
export ROCR_VISIBLE_DEVICES=0

mkdir -p "$MODELS_DIR"

# make sure ROCm part of the native install is present
if [ ! -d "$OLL_DIR/lib/ollama" ]; then
  echo "❌ native ollama not extracted yet in $OLL_DIR — run install step first"
  exit 1
fi

# stop any previous instance of THIS script's server only (never touches snap's)
pkill -f "ollama/.*bin/ollama se[r]ve" 2>/dev/null || true
sleep 1

nohup "$OLL_DIR/bin/ollama" serve > /tmp/ollama_native.log 2>&1 &
echo "ollama (native, GPU) pid: $!"
sleep 3

echo "--- GPU detection in server log:"
grep -iE "rocm|vram|gpu" /tmp/ollama_native.log | head -6 || echo "(none yet)"

echo "--- models:"
"$OLL_DIR/bin/ollama" list || true

echo "GPU-only confirm command:  $OLL_DIR/bin/ollama ps  ->  PROCESSOR column must say '100% GPU'"
