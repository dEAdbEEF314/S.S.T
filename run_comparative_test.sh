#!/bin/bash
model_id=$1
gguf_name=$2
appids=("1027880" "1113510" "1167720")
BASE_DIR="$(pwd)"

echo "--- 🧪 Testing Model: $model_id ($gguf_name) ---"
sed -i "s/LLM_MODEL=.*/LLM_MODEL=$model_id/" .env

docker stop sst-llama-server 2>/dev/null || true
docker rm sst-llama-server 2>/dev/null || true
docker run -d --name sst-llama-server \
  --gpus all \
  -v "${BASE_DIR}/Models/blobs:/models" \
  -p 11435:8080 \
  ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m "/models/$gguf_name" \
  -c 32768 \
  --n-gpu-layers 99 \
  --parallel 2 \
  --host 0.0.0.0 --port 8080

loaded=false
for i in {1..12}; do
  sleep 5
  if docker logs sst-llama-server 2>&1 | grep -q "server is listening"; then
    loaded=true
    break
  fi
  if docker logs sst-llama-server 2>&1 | grep -q "error loading model"; then
    echo "❌ Model failed to load: $gguf_name"
    break
  fi
done

if [ "$loaded" = true ]; then
  echo "✅ Model loaded successfully. Starting tests..."
  for appid in "${appids[@]}"; do
    echo "  - Processing AppID $appid..."
    export PYTHONPATH="${BASE_DIR}/src" && uv run python -m scout.main --appid "$appid" --dev --force
  done
else
  echo "⏭️ Skipping $model_id"
fi
