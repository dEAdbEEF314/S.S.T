#!/bin/bash
# ==============================================================================
# S.S.T Local LLM Setup Script for RTX 4090 Laptop (16GB VRAM)
# Target OS: WSL2-Ubuntu 24.04
# Architecture: Native Ollama (Dynamic Context & Speculative Decoding)
# ==============================================================================

set -e

echo "--- 🚀 S.S.T Local LLM (Native Ollama) Setup Started ---"

# 1. Install Dependencies & Ollama
echo "--- 📦 Checking Dependencies... ---"

if ! command -v ollama &> /dev/null; then
    echo "--- 📦 Installing Ollama... ---"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "--- ✅ Ollama is already installed. ---"
fi

# 2. Verify Ollama Server is Running
echo "--- 🔍 Verifying Ollama Server... ---"
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "⚠️ Ollama server is not running."
    if command -v systemctl &> /dev/null && ps -p 1 -o comm= | grep -q systemd; then
        echo "Attempting to start ollama via systemd..."
        sudo systemctl start ollama
        sleep 3
    else
        echo "Please run 'ollama serve' in another terminal and try again."
        exit 1
    fi
fi

# 3. Pull Base Models
echo "--- 📥 Pulling Base Models ---"
ollama pull qwen2.5:1.5b # For Draft
ollama pull qwen2.5:7b   # For Small
ollama pull qwen3.5:9b   # For Medium
ollama pull phi4:14b     # For Large


echo -e "\n--- ✅ Setup Complete! ---"
echo "Make sure to update your .env file:"
echo "LLM_BACKEND=OLLAMA"
echo "LLM_BASE_URL=http://localhost:11434"
echo "LLM_DRAFT_MODEL=qwen2.5:1.5b"
echo "MAX_PARALLEL_ALBUMS=2"
echo "------------------------------------------"
echo "Tip: For massive context with limited VRAM, consider setting:"
echo "export OLLAMA_KV_CACHE_TYPE=q4_0"
echo "in your .bashrc or systemd service."
