# S.S.T 設定ガイド

## 1. 方針

設定値は処理能力、接続先、言語などの実行条件を変えられますが、情報ソースの優先順位そのものは変えません。

次は固定ルールです。

- STEAM は構造の正
- TPE1 は ACOUSTID 優先
- MBZ tie-break は Digital Media 優先
- Bandcamp は MBZ 候補から除外寄りに扱う
- 変換元の優先順位は Tier で固定

`.env.example` はConfigの既定値を複製するファイルではなく、Ollama向けの推奨実行profileです。`LLM_BACKEND`、`LLM_MODEL`、`LLM_OLLAMA_NUM_CTX`、`LLM_OLLAMA_NUM_PREDICT` はConfig既定値と異なる明示設定です。また `LLM_REQUEST_PARALLELISM_MAX_WORKERS` はConfig既定4に対してsampleを2とし、`METADATA_FIELD_FALLBACK_PRIORITY` はlegacy値に影響されないようsampleで明示しています。API keyやcookieの`your_*`値は置換用placeholderであり、実際のsecretではありません。

---

## 2. システム・Steam・ローカル設定

### 2.1 Steam 関連

- `STEAM_INSTALL_PATH`: Steam インストールパス (必須)
- `STEAM_LOGIN_SECURE`: dynamicstore / ストア情報取得用クッキー
- `STEAM_PICS_BRIDGE_URL`: PICS 情報取得ブリッジURL（既定: `http://localhost:8080/v1/info/`）
- `STEAM_PICS_BRIDGE_API_KEY`: PICS Bridge 認証用キー (任意)
- `STEAM_WEB_API_KEY`: Steam Web API キー (任意)
- `STEAM_LIBRARY_PATH`: 特定のライブラリフォルダのみを対象にする場合のパス (任意)

### 2.2 出力とローカル状態

- `SST_OUTPUT_DIR`: 成果物 ZIP の出力先ディレクトリ（既定: `output`）
- `SST_LOG_DIR`: 実行ログの出力先ディレクトリ（既定: `logs`）
- `SST_LOCK_PATH`: 多重起動防止用lockファイル（既定: `data/sst.lock`）
- `SST_USERDATA_PATH`: Steam userdata JSONの保存先（既定: `data/userdata.json`）
- `SST_STEAM_CACHE_PATH`: Steamスキャンキャッシュの保存先（既定: `data/sst_cache.json`）
- `SST_STEAM_TAG_CACHE_PATH`: Steam公式タグ名称cacheの保存先（既定: `data/steam_tags.json`）
- `SST_AUDIT_REPORT_DIR`: 自動監査レポートの出力先（既定: `report`）
- `AUTO_AUDIT_ENABLED`: バッチ完了後の自動監査レポート生成（既定: `true`）
- `SST_WORKING_DIR`: 一時作業ディレクトリ（既定: `/tmp/sst-work`）
- `SST_DB_PATH`: 状態記録用 SQLite データベースのパス（既定: `data/sst_local_state.db`）
- `SST_DEFERRED_COPY_DELAY_SECONDS`: 共有ストレージへの copy に失敗した track を通常バッチ完了後に一度だけ再試行するまでの待機秒数（既定: 600秒）。0を指定すると待機せずに居残り再試行を実施。
- `MAX_ENCODING_TASKS`: 音声エンコード処理の最大同時タスク数（既定: 4）
- `USER_LANGUAGE`: メタデータ言語（既定: `ja`）
- `STEAM_TAG_CACHE_REFRESH_DAYS`: 公式 Steam タグ名称の再取得間隔（既定: 30日）
- `LOG_LEVEL`: ログ出力レベル（既定: `INFO`）

### 2.3 Steam ネットワーク・タイムアウト・スロットリング

API の輻輳やレート制限を防ぎ、通信エラーに対する復旧性を高める設定です。

- `STEAM_API_TIMEOUT`: Steam Store API 呼び出しのタイムアウト秒数（既定: 15.0）
- `STEAM_USERDATA_TIMEOUT`: Steam userdata取得のタイムアウト秒数（既定: 10.0）
- `STEAM_PICS_TIMEOUT`: Steam PICS Bridge 呼び出しのタイムアウト秒数（既定: 30.0）
- `STEAM_API_MAX_RETRIES`: リクエスト失敗時の最大再試行回数（既定: 3）
- `STEAM_API_RETRY_DELAY`: Steam API再試行の初期待機秒数（既定: 2.0）
- `STEAM_API_RETRY_BACKOFF`: 再試行ごとの指数待機倍率（既定: 2.0、1以上）
- `STEAM_THROTTLE_DELAY`: Store API 連続アクセス前の基本スロットリング待機秒数（既定: 2.0秒。0〜1秒のランダムジッターが付与されます）

### 2.4 パッケージング & パフォーマンス最適化設定

- `ZIP_COMPRESSION_STRATEGY`: ZIP パッケージングの圧縮方式（既定: `auto`）
  - `auto`: FLAC, MP3, JPG, PNG などのすでに圧縮済みのマルチメディアファイルは無圧縮（`ZIP_STORED`）で保存し、テキスト、JSON、CUE シートなどのメタデータのみ DEFLATE 圧縮するハイブリッド方式です。
  - `stored`: 全ファイルを無圧縮（`ZIP_STORED`）で保存（超高速 I/O）。
  - `deflate`: 全ファイルを DEFLATE 圧縮（従来の挙動）。
- `ZIP_DEFLATE_LEVEL`: DEFLATE 圧縮時の圧縮レベル 1〜9（既定: 1 / 最高速）。
- `FFPROBE_TIMEOUT`: `ffprobe` のタイムアウト秒数（既定: 10.0）。音源durationおよびロスレス音声プロパティ（sample_rate, bit_depth）はMutagenによるヘッダ抽出を優先し、失敗時のみffprobeへフォールバックします。
- `FFMPEG_TIMEOUT`: `ffmpeg` エンコードのタイムアウト秒数（既定: 600.0）。
- `IMAGE_DOWNLOAD_TIMEOUT`: カバーアート画像ダウンロードのタイムアウト秒数（既定: 15.0）。
- `IMAGE_DOWNLOAD_MAX_BYTES`: カバーアート画像ダウンロードの最大許容サイズ（既定: 25MB = 26,214,400 bytes）。超過時は安全に中止します。

---

## 3. LLM 設定

### 3.1 必須項目

- `LLM_BACKEND`: `OLLAMA` | `GEMINI` | `OPENAI_COMPATIBLE` | `LITELLM`（既定: `GEMINI`）
- `LLM_BASE_URL`: LLM 接続先エンドポイント URL（既定: `http://localhost:11434`）
- `LLM_API_KEY`: API キー（LiteLLM ではプロバイダー標準の環境変数で代替可能）
- `LLM_MODEL`: 使用モデル名（既定: `gemini-1.5-pro`。例: `ornith:9b`）
- `LLM_DRAFT_MODEL`: Ollama speculative decoding用draft model（任意）

### 3.2 タイムアウト・信頼性制御

- `LLM_HEALTH_CHECK_TIMEOUT`: LLM サーバー稼働確認時のタイムアウト秒数（既定: 10.0）
- `LLM_PREFLIGHT_TIMEOUT`: VRAM推定前のモデルwarm-up要求タイムアウト秒数（既定: 120.0）
- `LLM_RETRY_DELAY`: 呼び出し失敗時の初期待機秒数（既定: 5.0）
- `LLM_RETRY_BACKOFF`: 再試行時の指数バックオフ倍率（既定: 1.5）
- `LLM_REQUEST_TIMEOUT`: 1リクエストの最大タイムアウト秒数（既定: 3600）
- `LLM_MAX_RETRIES`: 最大再試行回数（既定: 3）

### 3.3 チューニング・並列制御

- `MAX_PARALLEL_ALBUMS`: 全体並列アルバム処理数（既定: 2）
- `LLM_LIMIT_RPM`: クラウド API の分あたりリクエスト制限（既定: 15）
- `LLM_LIMIT_TPM`: クラウド API の分あたりトークン制限（既定: 10000000）
- `LLM_LIMIT_RPD`: クラウド API の日あたりリクエスト制限（既定: 1500）
- `LLM_CLOUD_MAX_TOKENS`: クラウド API の最大トークン数（既定: 8192）
- `LLM_OLLAMA_NUM_CTX`: Ollama の最大コンテキストトークン（既定: 32768）
- `LLM_OLLAMA_NUM_PREDICT`: Ollama の最大出力トークン（既定: 8192）
- `LLM_OLLAMA_THINK`: Ollama での思考トークン出力（既定: false）
- `LLM_OLLAMA_PARALLEL_SLOTS`: llama-server / Ollama の実効 sequence slot 数（既定: 4）
- `LLM_VRAM_SCHEDULING_ENABLED`: VRAM 推計に基づく並列制御（既定: true）
- `LLM_REQUEST_PARALLELISM_ENABLED`: リクエスト並列化有効フラグ（既定: true）
- `LLM_REQUEST_PARALLELISM_MAX_WORKERS`: 並列 worker 数（`Config` の既定: 4、`.env.example` の推奨設定: 2）
- `LLM_ALBUM_TIER_SMALL_MAX_TRACKS`: Small Tier 最大曲数（既定: 50）
- `LLM_ALBUM_TIER_MEDIUM_MAX_TRACKS`: Medium Tier 最大曲数（既定: 100）
- `LLM_OLLAMA_NUM_CTX_SMALL / MEDIUM / LARGE`: Tier別context token上限
- `LLM_REQUEST_PARALLELISM_MAX_WORKERS_SMALL / MEDIUM / LARGE`: Tier 別 worker 数
- `LLM_FORCE_COHERENCE_LARGE`: 大型アルバムでの Coherence 強制実行（既定: true）
- `LLM_OUTPUT_BUDGET_SAFETY_RATIO`: 動的トークン天井の安全マージン比率（既定: 0.25）
- `LLM_ADAPTIVE_DEGRADED_PROMPT_ENABLED`: トークン上限到達時の縮退プロンプト自動適用（既定: true）
- `LLM_CHUNK_SIZE_VIRTUAL`: 仮想トラックalignmentのchunk上限（既定: 20）
- `LLM_CHUNK_SIZE_METADATA_OLLAMA`: Ollama向けmetadata chunkのトラック数上限（既定: 10）
- `LLM_CHUNK_SIZE_METADATA_CLOUD`: cloud向けmetadata chunkのトラック数上限（既定: 30）
- `LLM_CHUNK_ADAPTIVE`: 実行profileに応じたchunkサイズ調整（既定: true）
- `LLM_CHUNK_OUTPUT_TOKENS_PER_TRACK`: trackごとの出力トークンbudget見積もり（既定: 180）
- `LLM_CHUNK_OUTPUT_SAFETY_RATIO`: chunk出力budgetの安全比率（既定: 0.75）
- `LLM_OLLAMA_NUM_CTX_SMALL`, `LLM_OLLAMA_NUM_CTX_MEDIUM`, `LLM_OLLAMA_NUM_CTX_LARGE`: album tier別context トークン上限（既定: 8192 / 16384 / 32768）
- `LLM_REQUEST_PARALLELISM_MAX_WORKERS_SMALL`, `LLM_REQUEST_PARALLELISM_MAX_WORKERS_MEDIUM`, `LLM_REQUEST_PARALLELISM_MAX_WORKERS_LARGE`: tier別request worker上限（既定: 3 / 2 / 1）
- `SST_LLM_CACHE_ENABLED`: identity/tracklist LLM結果cache（既定: true）。hit結果も通常の正規化とvalidationを通過します。
- `SST_LLM_CACHE_TTL_SECONDS`: LLM結果cacheのTTL秒数（既定: 86400）
- `SST_LLM_CACHE_PATH`: LLM結果cache JSONの保存先（既定: `data/llm_cache.json`）
- `METADATA_FIELD_FALLBACK_PRIORITY`: 監査レポートのsource matrix表示順（既定: `STEAM,ACOUSTID,MBZ_RELEASE,MBZ_SEARCH,EMBED,LOCAL`）。実際のタグ選択や固定されたsource authorityは変更しません。
- `METADATA_SOURCE_PRIORITY`: 旧設定名。互換読み込み時に起動warningを出します。既存値を直ちに`METADATA_FIELD_FALLBACK_PRIORITY`へ移し、旧キーを削除してください。両方が指定されている場合は新設定を使い、旧設定は無視します。旧名は将来削除予定です。
- `LLM_NUM_CTX`, `LLM_COHERENCE_THRESHOLD`, `TITLE_CLEANING_TRUSTED_SOURCES`: 未使用設定のため削除しました。現行の処理経路には影響しません。

---

## 4. 外部メタデータ API 連携 (MusicBrainz & AcoustID)

- `MBZ_APP_NAME`: MusicBrainz 問い合わせ時のアプリケーション名（既定: `SST-Scout`）
- `MBZ_APP_VERSION`: アプリケーションバージョン（既定: `1.0.0`）
- `MBZ_CONTACT`: 連絡先メールアドレス（既定: `contact@example.lan`。運用時は有効な連絡先を指定）
- `MBZ_RATE_LIMIT_DELAY`: MusicBrainz API 連続アクセス待機秒数（既定: 1.0秒）
- `MBZ_SEARCH_LIMIT`: MusicBrainz 検索候補の最大取得件数（既定: 20）
- `ACOUSTID_API_KEY`: AcoustID API クライアントキー
- `ACOUSTID_TIMEOUT`: AcoustID API タイムアウト秒数（既定: 10.0）
- `ACOUSTID_RATE_LIMIT_WAIT_MIN`: AcoustID レートリミット最小待機秒数（既定: 1.5）
- `ACOUSTID_RATE_LIMIT_WAIT_MAX`: AcoustID レートリミット最大待機秒数（既定: 2.0）
- `SST_FINGERPRINT_ALL`: 全トラックの音声指紋スキャン（既定: true）。false の場合は代表サンプルのみスキャン。
- `SST_FINGERPRINT_SAMPLE_SIZE`: `SST_FINGERPRINT_ALL=false` 時に均等抽出する代表トラック数（既定: 3）

---

## 5. MusicBrainz スコアリング設定

- `SCORE_MBZ_DIRECT_STEAM_LINK`: 500点（既定）
- `SCORE_MBZ_PARENT_STEAM_LINK`: 300点（既定）
- `SCORE_MBZ_DIRECT_STEAMDB_LINK`: 500点（既定）
- `SCORE_MBZ_PARENT_STEAMDB_LINK`: 300点（既定）
- `SCORE_MBZ_BANDCAMP_LINK`: 100点（既定）
- `SCORE_MBZ_TITLE_SIMILARITY_MAX`: 100点（既定）
- `SCORE_MBZ_TRACK_COUNT_MATCH`: 50点（既定）
- `SCORE_MBZ_TRACK_COUNT_PENALTY_PER_TRACK`: 20点/曲（既定）
- `SCORE_MBZ_TRACK_COUNT_PENALTY_MAX`: 300点（既定）
- `SCORE_MBZ_DIGITAL_FORMAT`: 30点（既定）
- `SCORE_MBZ_DATE_MATCH`: 20点（既定）
- `SCORE_MBZ_DATE_PENALTY_PER_YEAR`: 20点/年（既定）
- `SCORE_MBZ_DATE_PENALTY_MAX`: 100点（既定）
- `SCORE_MBZ_FINGERPRINT_MATCH`: 200点（既定）
- `SCORE_MBZ_DIRECT_RECORDING_MATCH`: 1000点（既定）
- `SCORE_MBZ_ACOUSTID_RELEASE_MATCH`: 1000点（既定）
- `SCORE_MBZ_PUBLISHER_LABEL_MATCH`: 100点（既定）
- `MIN_MBZ_SEARCH_SCORE_THRESHOLD`: 250点（既定）

---

## 6. 通知設定

- `NOTIFY_ENABLED`: 通知有効フラグ（既定: false）
- `NOTIFY_COOLDOWN`: 同一通知の抑制間隔秒数（既定: 60）
- `NOTIFY_REQUEST_TIMEOUT`: Webhook HTTP要求timeout秒数（既定: 10）
- `NOTIFY_MAX_RETRIES`: Webhook要求の最大試行回数（既定: 3、初回を含む）
- `NOTIFY_RETRY_DELAY`: 初回失敗後の待機秒数（既定: 2）
- `NOTIFY_RETRY_BACKOFF`: 再試行ごとの待機時間倍率（既定: 1.5、1以上）
- `DISCORD_WEBHOOK_CRITICAL`: 致命的エラー用 Webhook URL
- `DISCORD_WEBHOOK_WARNING`: 警告用 Webhook URL
- `DISCORD_WEBHOOK_INFO`: 情報通知用 Webhook URL
- `DISCORD_WEBHOOK_COMPLETION`: 完了通知用 Webhook URL

---

## 7. セキュリティ設定

- `SECURITY_BLOCK_PRIVATE_IPS`: SSRF (Server-Side Request Forgery) 防御（既定: `true`）。
  カバーアートや外部リソース取得時に、ループバック (`127.0.0.1`, `::1`)、プライベート IP (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)、リンクローカルおよびクラウドメタデータ IP (`169.254.169.254`)、`localhost` 等へのアクセスを遮断します。
- `SECURITY_MASK_SECRETS_IN_LOGS`: 機密情報自動マスキング（既定: `true`）。
  ログ、エラーメッセージ、通知ログに含まれる API キーや Discord Webhook トークン等のシークレットを自動的に `[REDACTED]` または `[REDACTED_WEBHOOK_TOKEN]` に難読化します。
- **.env ファイルのパーミッション警告**:
  起動時に `.env` のパーミッションを検証し、他ユーザーから読み取り可能（World-Readable）な場合に警告を出力して `chmod 600 .env` を促します。
