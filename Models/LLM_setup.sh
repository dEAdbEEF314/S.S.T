#!/bin/bash
# ==============================================================================
# S.S.T Local LLM Setup Script for RTX 4090 Laptop (16GB VRAM)
# Target OS: WSL2-Ubuntu 24.04
# Architecture: Docker (llama-server) + Ollama (for model pulling)
# ==============================================================================

set -e

echo "--- 🚀 S.S.T Local LLM (Docker llama-server) Setup Started ---"

# 1. Check for Docker and NVIDIA Toolkit
if ! command -v docker &> /dev/null; then
    echo "❌ Error: docker not found. Please install Docker Desktop or Docker Engine."
    exit 1
fi

if ! docker run --rm --gpus all ubuntu nvidia-smi &> /dev/null; then
    echo "❌ Error: Docker cannot access GPUs. Please install NVIDIA Container Toolkit."
    exit 1
fi

# 2. Install Ollama (Used ONLY as a model downloader)
if ! command -v ollama &> /dev/null; then
    echo "--- 📦 Installing Ollama (Downloader)... ---"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "--- ✅ Ollama is already installed. ---"
fi

# 3. Pull Base Models via Ollama
echo "--- 📥 Pulling Models via Ollama ---"
ollama pull qwen2.5:7b-instruct
ollama pull qwen3.5:9b
# ollama pull phi-4:14b

# 4. Extract Blobs for llama-server
echo "--- 🔗 Linking Models for llama-server ---"
mkdir -p Models/blobs

# Helper to find the largest blob for a pulled model
# Note: In a real scenario, you'd find the specific sha256 blob for the model. 
# Here we just instruct the user.
echo "⚠️ IMPORTANT: Ollama stores models in /usr/share/ollama/.ollama/models/blobs/"
echo "Please copy or symlink the target .gguf blob to Models/blobs/target_model.gguf"
echo "Example: sudo cp /usr/share/ollama/.ollama/models/blobs/sha256-xxx Models/blobs/qwen2.5-7b.gguf"

# 5. Start llama-server via Docker
echo "--- 🐳 Starting llama-server container ---"
echo "This configuration forces a 32768 context window and 2 parallel workers, bypassing Ollama's 4096 VRAM limit."

docker stop sst-llama-server 2>/dev/null || true
docker rm sst-llama-server 2>/dev/null || true

# Note: Adjust the -m parameter to the symlinked model you created above.
# docker run -d --name sst-llama-server \
#   --gpus all \
#   -v $(pwd)/Models/blobs:/models \
#   -p 11435:8080 \
#   ghcr.io/ggml-org/llama.cpp:server-cuda \
#   -m /models/qwen2.5-7b.gguf \
#   -c 32768 \
#   --n-gpu-layers 99 \
#   --parallel 2 \
#   --host 0.0.0.0 --port 8080

echo -e "\n--- ✅ Setup Complete! ---"
echo "Make sure to update your .env file:"
echo "LLM_BACKEND=OPENAI_COMPATIBLE"
echo "LLM_BASE_URL=http://localhost:11435/v1"
echo "MAX_PARALLEL_ALBUMS=2"
echo "------------------------------------------"
