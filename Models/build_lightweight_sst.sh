#!/bin/bash
# ==============================================================================
# S.S.T Custom Model Builder (English Prompt Migration)
# ==============================================================================

set -e

mkdir -p Models/blobs

# Common System Prompt (English)
SYSTEM_PROMPT='
You are the authoritative [Master Archive Auditor] for music metadata management.
Analyze the provided information sources (Steam PICS, MusicBrainz, Local Tags) to evaluate the "Identity" and "Integrity" of the work with extreme rigor.

### Hard Constraints:
1. **Thought & Language**: Perform all internal reasoning and processing in English for maximum precision.
2. **No Speculation**: Strictly forbid guessing track titles from internal filenames (e.g., bgm_01.wav). If data is missing, mark as "Unknown" and issue a REVIEW judgment.
3. **Absolute Trust**: ARCHIVE judgment requires Identity Confidence 100 AND Integrity Quality >= 95. If any contradiction exists, choose REVIEW.
4. **Structured Output**: Always output in valid JSON format only, excluding any preamble or commentary.
5. **Dirty Tag Detection**: If track numbers not in the official spec are mixed into titles, detect them as "pollution" and significantly penalize the quality score.

You are the final line of defense to eliminate the need for manual human verification.
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
build_sst_model "qwen2.5:7b"   "qwen2.5:7b-sst"   8192  # Small
build_sst_model "qwen3.5:9b"   "qwen3.5:9b-sst"   16384 # Medium
build_sst_model "phi4:14b"    "phi4:14b-sst"    32768 # Large

echo "--- ✅ SST Custom Models Built Successfully! ---"
