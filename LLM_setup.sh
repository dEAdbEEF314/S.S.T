#!/bin/bash
# ==============================================================================
# S.S.T Local LLM Setup Script for RTX 4090 Laptop (16GB VRAM)
# Target OS: WSL2-Ubuntu 24.04
# ==============================================================================

set -e

echo "--- 🚀 S.S.T Local LLM (Ollama) Setup Started ---"

# 1. Check for NVIDIA Driver in WSL2
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ Error: nvidia-smi not found. Please ensure NVIDIA Drivers are installed on Windows and WSL2 is updated."
    exit 1
fi

# 2. Install Ollama for Linux
echo "--- 📦 Installing Ollama... ---"
curl -fsSL https://ollama.com/install.sh | sh

# 3. Optimize Ollama for 16GB VRAM
echo "--- ⚙️ Optimizing Ollama Environment ---"
# WSL2のsystemdサービス設定を上書きして、GPUパフォーマンスを最大化
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat << 'EOF' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
# WSL2でdGPUを確実に掴むための環境変数
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_ORIGINS=*"
# VRAM 16GBを効率よく使うための設定
# 同時並列処理を制限してVRAM溢れを防ぐ（S.S.Tの安定性重視）
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
# Flash Attentionを有効化（4090で劇的に高速化）
Environment="OLLAMA_FLASH_ATTENTION=1"
# 必要に応じてVRAM 16GBギリギリまで使わせる
Environment="OLLAMA_MAX_VRAM=15500"
EOF

# 4. Restart Ollama with new settings
echo "--- 🔄 Restarting Ollama service... ---"
sudo systemctl daemon-reload
sudo systemctl restart ollama

# 5. Pull Recommended Models
# RTX 4090 16GB で最高のバランスを誇るモデルを選択
echo "--- 📥 Pulling LLM Models (This may take a few minutes) ---"

# 第1候補: Gemma 4 31B (4-bit量子化) - 知能重視
# 16GB VRAMの場合、Q4_K_M量子化がギリギリ収まり、高い推論能力を発揮します
echo "Downloading Gemma 4 31B (4-bit)..."
ollama pull gemma4:31b-4bit || echo "⚠️ Model gemma4 not found yet, trying Gemma 2 27b as fallback..." && ollama pull gemma2:27b

# 第2候補: Qwen 2.5 14B - 速度・正確性重視 (16GBなら爆速)
echo "Downloading Qwen 2.5 14B..."
ollama pull qwen2.5:14b

# 6. Verification
echo -e "\n--- ✅ Setup Complete! ---"
echo "Ollama is running at: http://localhost:11434"
echo "GPU Status in Ollama:"
ollama ps || echo "Ollama is idling."

echo -e "\n--- 📝 Next Step: Update your .env file ---"
echo "LLM_BASE_URL=http://localhost:11434/v1"
echo "LLM_API_KEY=ollama"
echo "LLM_MODEL=gemma4:31b-4bit  # or gemma2:27b or qwen2.5:14b"
echo "------------------------------------------"
