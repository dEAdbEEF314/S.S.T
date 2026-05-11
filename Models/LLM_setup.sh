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

# 2. Install Ollama for Linux (if not already installed)
if ! command -v ollama &> /dev/null; then
    echo "--- 📦 Installing Ollama... ---"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "--- ✅ Ollama is already installed. ---"
fi

# 3. Optimize Ollama for 16GB VRAM
echo "--- ⚙️ Optimizing Ollama Environment ---"
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat << 'EOF' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_ORIGINS=*"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_MAX_VRAM=15500"
EOF

echo "--- 🔄 Restarting Ollama service... ---"
sudo systemctl daemon-reload
sudo systemctl restart ollama || echo "⚠️ Could not restart ollama service via systemctl. Please restart it manually if needed."

# 4. Pull and Build SST Specialized Models
echo "--- 📥 Preparing SST Specialized Models ---"

function build_sst_model() {
    local base_model=$1
    local modelfile=$2
    local sst_name=$3
    
    echo "Processing $base_model..."
    ollama pull "$base_model"
    echo "Building $sst_name..."
    ollama create "$sst_name" -f "$modelfile"
}

# --- Recommended Models ---
build_sst_model "qwen3.5:9b" "Models/SST_Qwen3.5_9B_Modelfile" "qwen3.5-9b-sst"
build_sst_model "huihui_ai/huihui-moe-abliterated:12b" "Models/SST_Huihui_12B_Modelfile" "huihui-12b-sst"
build_sst_model "granite4.1:8b" "Models/SST_Granite_8B_Modelfile" "granite-8b-sst"

# --- Legacy/Compatible Models ---
# build_sst_model "qwen2.5:14b" "Models/SST_Modelfile" "qwen2.5-14b-sst"
# build_sst_model "qwen2.5:7b" "Models/SST_7B_Modelfile" "qwen2.5-7b-sst"

# 5. Verification
echo -e "\n--- ✅ Setup Complete! ---"
echo "Available SST Models:"
ollama list | grep sst

echo -e "\n--- 📝 Next Step: Update your .env file ---"
echo "LLM_MODEL=qwen3.5-9b-sst  # Recommended for RTX 4090"
echo "LLM_MODEL=huihui-12b-sst  # High Intelligence alternative"
echo "LLM_MODEL=granite-8b-sst   # Consistent & Robust alternative"
echo "------------------------------------------"
