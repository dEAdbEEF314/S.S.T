# Token Stingy (VRAM最適化とコンテキスト動的算出アーキテクチャ)

ローカル環境（Ollama等）でLLM推論を並列処理させる際、すべてのリクエストに対してLLMの最大コンテキストサイズ（例: 8192トークン）を割り当てると、即座にVRAMが枯渇し、OOM（Out of Memory）エラーやパフォーマンスの著しい低下を招きます。

本ドキュメントでは、S.S.Tの**「厳密に構造化されたJSON出力」**という特性を活かし、リクエストごとに必要最小限のコンテキストサイズ（`num_ctx`）を事前計算し、並列処理効率を最大化する手法（Token Stingy戦略）について解説します。

## 1. 算出ロジックの概要

S.S.TのLLM連携は、長文のテキスト生成ではなく「JSONの穴埋めと構造化データ変換」です。そのため、入出力トークン数を極めて高い精度で事前予測できます。

必要最小限の `num_ctx` は以下の計算式で決定されます。
```
必要コンテキスト (num_ctx) = 入力予測トークン数 + 出力予測トークン数
```

### 1-1. 入力予測トークン数の算出 (ヒューリスティック法)
完成したプロンプト文字列の長さ（バイト/文字数）から、トークナイザーの特性に基づき概算します。外部ライブラリ（tiktoken等）に依存しない最速の手法です。
- 英語ベースのJSONやID3タグ情報が中心となるため、安全係数として **2.5文字 = 1トークン** を基準とします。
- `入力予測トークン数 = int(len(prompt_string) / 2.5)`

### 1-2. 出力予測トークン数の算出 (スキーマ制約法)
S.S.Tの出力は2種類のJSONスキーマに分かれており、それぞれ上限が物理的（ID3v2.3規格等）に定まっています。

* **A. 全体監査 (Global Audit) プロンプト**
  * 内容: 判定ステータス、戦略（Enum）、主要タグ、1〜2文の判定理由。
  * 予測: 理由が長引いたとしても最大 **500トークン** を超えることはありません。
* **B. トラックマッピング (Track Mapping) プロンプト**
  * 内容: チャンク化されたトラック群のマッピング指示。
  * 予測: 1トラック分のマッピング指示（JSON構造、ID、理由等）は約 80〜100トークン に収束します。
  * 計算: `チャンク内のトラック数 × 100 トークン`（最大チャンクが20曲なら2000トークン）。

## 2. 組み込み実装イメージ

上記を統合し、`llm.py` などでOllama APIへリクエストを送信する直前に、ペイロードへ注入する `num_ctx` を決定します。

```python
def calculate_optimal_num_ctx(prompt_string: str, is_global_audit: bool, track_count_in_chunk: int = 0) -> int:
    # 1. 入力トークン概算
    input_tokens = int(len(prompt_string) / 2.5)
    
    # 2. 出力トークン予測
    if is_global_audit:
        expected_output_tokens = 500
    else:
        expected_output_tokens = track_count_in_chunk * 100
        
    # 3. 必要な最小トークン数を算出
    required_ctx = input_tokens + expected_output_tokens
    
    # 4. Ollamaなどの仕様に合わせ、2の累乗へ丸める（推奨: 下限2048、上限8192）
    if required_ctx <= 2048:
        return 2048
    elif required_ctx <= 4096:
        return 4096
    else:
        return 8192
```

リクエストペイロードへの適用例：
```python
payload = {
    "model": "qwen2.5:14b",
    "prompt": prompt,
    "format": "json", # ★重要（後述）
    "options": {
        "num_ctx": calculate_optimal_num_ctx(prompt, ...)
    }
}
```

## 3. 必須の安全対策：「Thinking」暴走の抑制

出力トークン数の予測が崩れる（OOMや無限処理ループに陥る）唯一の例外は、**LLMが指示（NO PREAMBLE 等）を無視し、JSONを出力する前に自己の思考プロセス（Chain of Thought）を長文で出力し始めた場合**です。

この不確実性を排除し、Token Stingy戦略を安全に機能させるためには、APIリクエスト時に **`"format": "json"`** パラメータを必ず付与し、LLMに「JSONフォーマット以外の出力（余計な思考プロセスのテキスト等）をシステムレベルで強制的に禁止する」措置を講じる必要があります。これにより、出力トークン数は完全に予測可能となります。
