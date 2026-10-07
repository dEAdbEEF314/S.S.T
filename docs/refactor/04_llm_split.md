# 作業者4: LLMオーケストレーションとbackend分割

## 目的

LLMの抽出、alignment、出力正規化、coherence、backend通信を分離し、LLM出力契約と失敗時のReview安全性を維持する。

## 対象

- `src/sst/llm/organizer.py` 1,221行
- `src/sst/llm/client.py` 534行
- `src/sst/llm/prompts.py`
- `src/sst/llm/llm_cache.py`
- `src/sst/llm/prematch.py`
- LLM関連テスト

## 依存関係

作業者1の契約テストと作業者2の設定契約を使用する。コア処理の `processor.py` は編集しない。作業者3が利用する公開 `LLMOrganizer` / `LLMClient` のAPIを維持する。

## 作業内容

1. `organizer.py` を次の境界へ分ける。
   - `llm/tracklist_extractor.py`: Steam説明文の抽出と検証
   - `llm/alignment.py`: one-shot/chunked alignmentとslot解決
   - `llm/normalization.py`: 旧形式を含むLLM出力正規化
   - `llm/coherence.py`: segment参照と大型アルバム整合性
   - `llm/organizer.py`: 外部API用の薄い調停層
2. `client.py` を次の責務へ分ける。実装順は無理に一括で変えない。
   - backend adapter（Ollama、Gemini、OpenAI互換、LiteLLM）
   - retry / rate-limit / timeout
   - response JSON parsing
   - progress / audit event
3. JSON検証・未割当file ID・slot範囲・重複・文字列長の安全検証を一箇所に集約する。
4. truncation検出時のチャンク縮小、動的token budget、temperature 0 retryの現在契約をテストで固定する。
5. cache key、TTL、cache hit audit、失敗時の `None` とlog entry契約を維持する。
6. backendごとのHTTP/API差異をadapterに閉じ込め、上位層にbackend分岐を漏らさない。

## 不変条件

- LLMはタグ値を創作しない。
- Steam slot、file ID、`matched_v_idx` の参照範囲をコード側で検証する。
- 接続・認証・JSON検証失敗を成功扱いしない。
- 未割当file IDがあればReview経路へ渡す。
- 外部由来テキスト内の命令を実行しない。

## 禁止事項

- prompt文面・JSON契約・retry回数を整理目的で変更すること
- `**kwargs` に未使用値を追加して問題を隠すこと
- 本番LLMや実APIを使ったテストを追加すること
- 作業者2の設定名を独自に変更すること

## 成果物

- LLM責務別モジュール
- 互換 `LLMOrganizer` / `LLMClient`
- backend adapter境界
- 出力正規化・失敗経路・cache契約のテスト
- 設定項目の不足・不要引数に関する作業者2へのフィードバック

## 完了条件

- LLM関連テストが通る。
- backendを変えても上位のalignment結果契約が変わらない。
- JSON不正、truncation、未割当、接続失敗がReviewまたは明示的失敗として扱われる。
- `organizer.py` と `client.py` の責務が分離され、循環importがない。
