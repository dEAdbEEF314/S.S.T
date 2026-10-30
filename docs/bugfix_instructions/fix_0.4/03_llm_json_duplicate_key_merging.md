# 修正指示書 03: LLM JSON レスポンスにおける重複スロットキーの非破壊マージ

## 1. 背景と課題

AppID `466530` (Koihime Enbu) において、LLM（Phase 2）が応答JSONを生成する際に、同一スロットキー（例: `"1_23"`）を複数回出力する事象が発生した：
- 前半で正常なマッピング `"1_23": {"files": ["track23.flac"], "reason": "match"}` を出力。
- レスポンスの末尾で再度 `"1_23": {"files": []}` を出力。

Python標準の `json.loads` は、キーが重複した場合に「後勝ち」で上書きする仕様となっている。このため、前半で正常に解決されたマッピングが空配列で上書きされて消失し、スロット欠損（未割当残留）として誤ってReview送りとなっていた。

## 2. 解決方針

1. **`object_pairs_hook` による安全な非破壊マージ**:
   - `src/sst/llm/response_parser.py` 内の `json.loads` に `object_pairs_hook=_merge_json_object_pairs` を導入する。
   - 同一キーが重複して現れた場合、既存のマッピング（空でないファイルリストや理由）を優先保持し、空リストによる意図しない上書きを防止する。
   - リスト同士の場合は順序を維持しつつユニーク結合を行う。

## 3. 実装詳細

### `src/sst/llm/response_parser.py`
- `_merge_json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]` 関数を実装。
- `parse_llm_response` 内の `json.loads` 呼び出し箇所すべてに `object_pairs_hook=_merge_json_object_pairs` を適用。

