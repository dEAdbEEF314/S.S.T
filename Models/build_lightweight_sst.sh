#!/bin/bash
# ==============================================================================
# S.S.T Custom Model Builder (English Prompt Migration)
# ==============================================================================

set -e

mkdir -p Models/blobs

# Common System Prompt (Direct JSON)
SYSTEM_PROMPT='
You are a [Metadata Audit JSON Generator].
Your ONLY output is a raw JSON object. 

RULES:
1. Start your response with "{" immediately.
2. DO NOT use reasoning blocks, "Thinking Process", or any preamble.
3. Output MUST be valid JSON.
4. If uncertain, default to judgment "REVIEW" and confidence 0.
'

build_sst_model() {
    local base_name=$1
    local custom_name=$2
    local ctx_size=${3:-8192}
    local safe_name=$(echo "$custom_name" | tr ':' '_')
    local mfile="Models/SST_${safe_name}_Modelfile"

    echo "--- 🛠️ Building $custom_name from $base_name (ctx: $ctx_size) ---"
    
    cat <<EOF > "$mfile"
FROM $base_name

# --- Inference Parameters ---
PARAMETER temperature 0
PARAMETER num_ctx $ctx_size
PARAMETER num_predict 2048
PARAMETER repeat_penalty 1.1
PARAMETER top_k 40
PARAMETER top_p 0.9

# --- System Identity ---
SYSTEM """$SYSTEM_PROMPT"""
EOF

    ollama create "$custom_name" -f "$mfile"
}

# Standard Tiered Models
build_sst_model "qwen2.5:1.5b" "qwen2.5:1.5b-sst" 32768 # Draft / Very Small
build_sst_model "qwen2.5:7b"   "qwen2.5:7b-sst"   32768 # Small
build_sst_model "qwen3.5:9b"   "qwen3.5:9b-sst"   32768 # Medium
build_sst_model "phi4:14b"    "phi4:14b-sst"    32768 # Large

echo "--- ✅ SST Custom Models Built Successfully! ---"
