# S.S.T 設定ガイド

## 1. 方針

設定値は処理能力、接続先、言語などの実行条件を変えられますが、情報ソースの優先順位そのものは変えません。

次は固定ルールです。

- STEAM は構造の正
- TPE1 は ACOUSTID 優先
- MBZ tie-break は Digital Media 優先
- Bandcamp は MBZ 候補から除外寄りに扱う
- 変換元の優先順位は Tier で固定

## 2. 必須設定

### 2.1 Steam 関連

- STEAM_INSTALL_PATH
- STEAM_LOGIN_SECURE
- STEAM_PICS_BRIDGE_URL

用途:

- Steam ローカル構造の解決
- dynamicstore / ストア情報取得
- PICS 情報取得

### 2.2 出力とローカル状態

- SST_OUTPUT_DIR
- SST_WORKING_DIR
- SST_DB_PATH
- MAX_ENCODING_TASKS

## 3. LLM 設定

### 3.1 必須項目

- LLM_BACKEND
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL

### 3.2 並列・容量制御

- MAX_PARALLEL_ALBUMS
- LLM_LIMIT_RPM
- LLM_LIMIT_TPM
- LLM_LIMIT_RPD
- LLM_CLOUD_MAX_TOKENS
- LLM_OLLAMA_NUM_CTX
- LLM_OLLAMA_NUM_PREDICT
- LLM_VRAM_SCHEDULING_ENABLED
- LLM_REQUEST_PARALLELISM_ENABLED
- LLM_REQUEST_PARALLELISM_MAX_WORKERS
- LLM_ALBUM_TIER_SMALL_MAX_TRACKS
- LLM_ALBUM_TIER_MEDIUM_MAX_TRACKS
- LLM_OLLAMA_NUM_CTX_SMALL / MEDIUM / LARGE
- LLM_REQUEST_PARALLELISM_MAX_WORKERS_SMALL / MEDIUM / LARGE
- LLM_FORCE_COHERENCE_LARGE

これらは実行性能やタイムアウト耐性に影響しますが、メタデータの正誤判定規則を変えてはいけません。

Tier 制御の原則:

- Small / Medium / Large はアルバム曲数で自動選択される
- 各 tier の `num_ctx` と Phase 2 worker 数は、その tier 専用値があればそれを使う
- tier 専用値が未設定なら、従来の `LLM_OLLAMA_NUM_CTX` と `LLM_REQUEST_PARALLELISM_MAX_WORKERS` にフォールバックする
- `LLM_FORCE_COHERENCE_LARGE=true` の場合、大型アルバムでは通常しきい値未満でも Coherence を走らせて review 側へ倒す安全性を優先する

## 4. メタデータ関連設定

- USER_LANGUAGE: TLANとSteamユーザータグ取得に使う言語。`ja`なら日本語、`en`なら英語の公式ストアページを参照
- STEAM_TAG_CACHE_REFRESH_DAYS: Steam公式ページ上のタグIDと名称の紐づけを再検証する間隔（日）。既定値は30日
- MBZ_APP_NAME / MBZ_APP_VERSION / MBZ_CONTACT: MusicBrainz 利用時の識別情報
- ACOUSTID_API_KEY: ACOUSTID 参照用

## 5. 実装チューニング項目

.env.example には現行実装の内部チューニング値も含まれます。代表例:

- AUDIO_FORMAT_PRIORITY
- TITLE_CLEANING_TRUSTED_SOURCES
- LLM_COHERENCE_THRESHOLD
- LLM_CHUNK_SIZE_VIRTUAL
- LLM_CHUNK_SIZE_METADATA_OLLAMA
- LLM_CHUNK_SIZE_METADATA_CLOUD
- LLM_CHUNK_ADAPTIVE
- LLM_CHUNK_OUTPUT_TOKENS_PER_TRACK
- LLM_CHUNK_OUTPUT_SAFETY_RATIO
- SCORE_MBZ_*
- MIN_MBZ_SEARCH_SCORE_THRESHOLD

扱い方の原則:

- これらは候補探索や実行効率の調整用とみなす
- [docs/METADATA_SOURCE_SPEC.md](docs/METADATA_SOURCE_SPEC.md) の正ソース定義を上書きしてはならない
- 旧来概念に由来する値が残っていても、現行仕様の正本は新仕様書である

## 6. 通知設定

次は任意です。

- NOTIFY_ENABLED
- NOTIFY_COOLDOWN
- DISCORD_WEBHOOK_CRITICAL
- DISCORD_WEBHOOK_WARNING
- DISCORD_WEBHOOK_INFO
- DISCORD_WEBHOOK_COMPLETION

通知は運用補助であり、archive / review 判定ロジックには関与しません。