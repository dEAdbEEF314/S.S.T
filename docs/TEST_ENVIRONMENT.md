# S.S.T テスト環境仕様書

このドキュメントは、S.S.T のスタンドアロン CLI ロジックおよび API 統合を検証するための標準的なテスト環境を定義します。

## 1. コア・スタック
- **OS**: Ubuntu 24.04推奨
- **ランタイム**: `uv` によって管理された Python 3.12以上。
- **メディアエンジン**: FFmpeg (実行環境 の `PATH` 内で利用可能であること)。
- **データベース**: SQLite 3。

## 2. インフラストラクチャ (Local Environment)
「究極データ取得モード」の検証には、以下のコンポーネントが稼働している必要があります：
- **PICS Bridge**: `.env` で設定された `{STEAM_PICS_BRIDGE_URL}` および `{STEAM_PICS_BRIDGE_API_KEY}` でアクセス可能な環境をユーザが用意する。
- **LLMサービス**: ユーザー各自で用意した環境 (Gemini, Ollama, OpenAI互換API) が稼働し、`.env` で設定されていること。

## 3. データソース (検証ターゲット)
テストは、以下の代表的な AppID に対して実行することを推奨します。これらは運用上有用だった**代表例**であり、システムや自動テストにハードコードされた必須ケースではありません：
1.  **1027880** (A Dance of Fire and Ice OST): モダンな PICS トラックリストと MusicBrainz 直接リンクの検証。
2.  **1586580** (Narita Boy): 複雑なファイル名からのトラック番号補完 (`override_track`) の検証。
3.  **1270860** (Exit the Gungeon): FFmpeg 警告（invalid rice order）が発生するケースの検証。

## 4. 環境変数 (.env)
有効なテスト環境には以下が必須です：
- `STEAM_WEB_API_KEY`: コミュニティタグ取得用。
- `STEAM_PICS_BRIDGE_URL`: `.env` に設定。
- `LLM_BACKEND`: `GEMINI`, `OLLAMA` (Native Ollama 推奨) または `OPENAI_COMPATIBLE`。

## 5. 検証チェックリスト
- [ ] ローカル出力先（`./output` 等）への正しい ZIP アーカイブの生成と保存（展開なし）。
- [ ] `COMM` 欄に `親ゲーム名, 親ゲームSTEAMストアページURL, [タグ1/ タグ2]...` の情報が連結されていること。既存の埋め込みコメントがある場合は、その先頭保持も確認する。
- [ ] MP3 または aiff に対する正確な ID3v2.3 タグ付け。

## 6. LLM Parallelism Observation Runbook
Ollama側のスロット使用状況をSST側のリクエストスケジューリングと照合する際は、以下の手順に従ってください。

1. デバッグログを有効にして、範囲を限定したSSTの実行を開始し、出力を専用のファイルに書き出します。

```bash
cd /workspace/S.S.T
uv run python -m sst.main --appid 1027880 --dev
```

2. Ollamaのログを、相関スクリプトが解析可能なISOタイムスタンプ形式でエクスポートします。

```bash
sudo journalctl -u ollama -S "2026-07-10 09:35:00" -o short-iso > /tmp/ollama-short-iso.log
```

3. その実行のために作成されたSSTデバッグログを特定してください。

```bash
ls -1t logs/SST_DEBUG_*.log | head -n 1
```

4. Correlate SST `LLM_REQUEST_*` records with Ollama slot events.

```bash
uv run python Maintenance/analyze_llm_slot_correlation.py \
	--sst-log logs/SST_DEBUG_YYYYMMDDHHMMSS.log \
	--ollama-log /tmp/ollama-short-iso.log \
	--app-id 1027880
```

5. 出力はこの順序で読んでください。
- `peak_inflight_requests`: SST側が同時に何件の request を発行しようとしたか。
- `LLM_REQUEST_VRAM` / `LLM_REQUEST_RELEASE`: SST側の request-level VRAM 予約と解放。
- `slot_ids_seen`: Ollama側で実際に使われた slot ID。
- `http 200 /api/chat` と `client_aborted`: 正常終了とクライアント切断の数。

6. Interpretation guide.
- `peak_inflight_requests > 1` なのに `slot_ids_seen` が `{0: ...}` だけなら、Ollama側で単一 slot 運用か、同時実行に至る前に待機している可能性が高い。
- `LLM_REQUEST_VRAM` が複数並ぶのに `wait_seconds` が長い場合、SST側の VRAM gate が並列度を抑えている。
- `client_aborted` や `500 /api/chat` が多い場合、slot 利用率の問題ではなく、SST側タイムアウトや接続切断を優先して調査する。
