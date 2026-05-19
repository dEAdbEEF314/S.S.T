#!/bin/bash
mkdir -p Models/blobs
build_model() {
  local base=$1
  local mfile=$2
  cat <<EOF > "$mfile"
FROM $base
PARAMETER temperature 0
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
PARAMETER repeat_penalty 1.1
PARAMETER top_k 40
PARAMETER top_p 0.9
SYSTEM """
あなたは音楽メタデータ管理の権威ある【マスター・アーカイブ監査官】です。
提供された情報源（Steam PICS, MusicBrainz, Local Tags）を分析し、作品の「Identity（身元）」と「Integrity（品質）」を極めて厳格に評価してください。
### 鉄の掟 (Hard Constraints):
1. **思考と言語**: 常に「日本語」で思考し、出力しなさい。
2. **推論の禁止**: 内部的なファイル名（例: bgm_01.wav）から曲名を憶測することを厳禁します。データがない場合は「Unknown」とし、REVIEW判定を下しなさい。
3. **絶対的信頼**: ARCHIVE判定を出すには、Identity Confidence 100 かつ Integrity Quality 95以上が必須です。少しでも矛盾があれば迷わず REVIEW としなさい。
4. **構造化出力**: 常に有効な JSON 形式のみを出力し、余計な前置きや解説は一切排除しなさい。
5. **Dirty Tagsの検出**: 公式仕様にないトラック番号がタイトルに混入している場合、それを「汚れ」として検知し、品質スコアを大幅に減点しなさい。
あなたは人間による最終確認を不要にするための、最後の砦です。
"""
EOF
  ollama create "$base-sst" -f "$mfile"
}
copy_blob() {
  local model=$1
  local target=$2
  local manifest="/usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library/${model/:/\/}"
  if [ -f "$manifest" ]; then
    local digest=$(grep -oP "\""digest"\"":"\""sha256:\K[^"\""]+" "\""$manifest"\"" | xargs -n1 -I{} du -b /usr/share/ollama/.ollama/models/blobs/sha256-{} 2>/dev/null | sort -nr | head -n1 | grep -oP "\""sha256-\K.*"\"")
    if [ -n "$digest" ]; then
      cp "/usr/share/ollama/.ollama/models/blobs/sha256-$digest" "Models/blobs/$target"
      echo "✅ Copied $model to Models/blobs/$target"
    fi
  fi
}
build_model "qwen2.5:1.5b" "Models/SST_Qwen2.5_1.5B_Modelfile"
build_model "llama3.2:1b" "Models/SST_Llama3.2_1B_Modelfile"
build_model "llama3.2:3b" "Models/SST_Llama3.2_3B_Modelfile"
build_model "qwen3.5:0.8b" "Models/SST_Qwen3.5_0.8B_Modelfile"
build_model "qwen3.5:2b" "Models/SST_Qwen3.5_2B_Modelfile"
build_model "phi3.5:latest" "Models/SST_Phi3.5_Mini_Modelfile"
copy_blob "qwen2.5:1.5b" "qwen2.5-1.5b.gguf"
copy_blob "llama3.2:1b" "llama3.2-1b.gguf"
copy_blob "llama3.2:3b" "llama3.2-3b.gguf"
copy_blob "qwen3.5:0.8b" "qwen3.5-0.8b.gguf"
copy_blob "qwen3.5:2b" "qwen3.5-2b.gguf"
copy_blob "phi3.5:latest" "phi3.5-mini.gguf"
