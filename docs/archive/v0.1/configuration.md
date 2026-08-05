# S.S.T 設定変数・環境変数リファレンス

本ドキュメントでは、S.S.Tの挙動を制御するために `.env` ファイル（またはOSの環境変数）で指定可能なすべての設定値と、コード内に直接定義されているハードコーディング値（マジックナンバー）を一覧化しています。

## 1. `.env` 指定可能な設定値 (Environment Variables)
これらの値は `.env` に大文字または小文字で記述することで、システムデフォルト値を上書きできます。

### 1.1 パス・ディレクトリ・基本設定
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `STEAM_INSTALL_PATH` | (必須) | Steamクライアントのインストールディレクトリ（`steamapps` の親）。 |
| `STEAM_LIBRARY_PATH` | `None` | 追加のSteamライブラリパス。 |
| `SST_WORKING_DIR` | `/tmp/sst-work` | 作業用の一時ディレクトリ。音声変換などのバッファに利用。 |
| `SST_DB_PATH` | `data/sst_local_state.db` | 状態管理用SQLiteデータベースのパス。 |
| `SST_OUTPUT_DIR` | `output` | 処理完了後のパッケージ（ZIP等）やエラー品を格納するディレクトリ。 |
| `USER_LANGUAGE` | `ja` | ログやメタデータ検索時に優先する言語。 |
| `LOG_LEVEL` | `INFO` | システムのログ出力レベル（`DEBUG`, `INFO`, `WARNING`, `ERROR`）。 |

### 1.2 外部API・認証キー
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `STEAM_LOGIN_SECURE` | `None` | Steamの年齢制限・ログイン必須ページにアクセスするためのセッションCookie。 |
| `STEAM_PICS_BRIDGE_URL` | `http://localhost:8080/v1/info/` | ローカルで稼働させるSteam PICS用ブリッジサーバーのURL。 |
| `STEAM_PICS_BRIDGE_API_KEY`| `None` | PICSブリッジサーバーのアクセスキー（設定している場合）。 |
| `STEAM_WEB_API_KEY` | `None` | Steam Web APIにアクセスするためのパブリッシャーAPIキー。 |
| `ACOUSTID_API_KEY` | `None` | 音響指紋ルックアップに必要なAcoustIDのAPIキー。 |

### 1.3 LLM / Ollama 推論設定
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LLM_BACKEND` | `GEMINI` | 使用するLLMバックエンド（`OLLAMA` または `GEMINI` などを指定）。 |
| `LLM_BASE_URL` | `http://localhost:11434` | ローカルLLM（Ollama）のAPIベースURL。 |
| `LLM_MODEL` | `gemini-1.5-pro` | メインの推論モデル名。 |
| `LLM_DRAFT_MODEL` | `None` | 高速な一次推論などに使用する軽量モデル名（必要な場合）。 |
| `LLM_REQUEST_TIMEOUT` | `3600` | LLM通信のタイムアウト秒数（60分）。キュー待ち時間も含む。 |
| `LLM_OLLAMA_NUM_CTX` | `32768` | Ollamaに渡すコンテキストウィンドウ（トークン数）。 |
| `LLM_OLLAMA_NUM_PREDICT` | `4096` | Ollamaが生成する最大出力トークン数。 |
| `LLM_VRAM_SCHEDULING_ENABLED`| `True` | VRAM残量を監視し、モデルロードをスケジューリングするかどうか。 |
| `LLM_REQUEST_PARALLELISM_ENABLED`| `True` | LLMへのリクエストを並列化するかどうか。 |
| `LLM_REQUEST_PARALLELISM_MAX_WORKERS`| `4` | LLMへの最大並列リクエスト数。 |

### 1.4 LLM チャンク・階層別制御 (Token Stingy Profile)
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LLM_COHERENCE_THRESHOLD` | `75` | Coherenceマッチング時のしきい値。 |
| `LLM_CHUNK_SIZE_VIRTUAL` | `20` | バーチャルアルバム推論時のチャンクサイズ。 |
| `LLM_CHUNK_ADAPTIVE` | `True` | コンテキスト溢れ発生時にチャンクサイズを動的に縮小するかどうか。 |

### 1.5 バッチ処理・並列化設定
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `MAX_PARALLEL_ALBUMS` | `2` | 同時に処理を進めるアルバムの最大数。 |
| `MAX_ENCODING_TASKS` | `4` | 音声変換（ffmpeg等）を並列実行する最大スレッド数。 |
| `FINGERPRINT_ALL` | `True` | すべてのトラックに対して音響指紋（AcoustID）の生成を試みるかどうか。 |
| `AUTO_AUDIT_ENABLED` | `True` | 処理後の自動監査（バリデーション）を有効にするかどうか。 |

### 1.6 通知設定 (Discord Webhook)
| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `NOTIFY_ENABLED` | `False` | 通知機能を有効にするかどうか。 |
| `NOTIFY_COOLDOWN` | `60` | 同じ通知を連投しないためのクールダウン秒数。 |
| `DISCORD_WEBHOOK_CRITICAL` | `None` | 致命的なエラー発生時の通知先Webhook URL。 |
| `DISCORD_WEBHOOK_WARNING` | `None` | Reviewへの降格など、警告レベルの通知先Webhook URL。 |
| `DISCORD_WEBHOOK_INFO` | `None` | 一般的なシステム通知用のWebhook URL。 |
| `DISCORD_WEBHOOK_COMPLETION`| `None` | 処理完了時のレポート通知先Webhook URL。 |

---

## 2. ハードコーディングされている設定値 (Hardcoded Values)
システム要件や外部APIの制限により、コード内に直接記述されている設定値です（`.env` では変更できません）。設定ファイルへの露出が必要になった場合は該当ソースコードをリファクタリングしてください。

### 2.1 外部API・ネットワーク通信のタイムアウトと待機
* **MusicBrainz API (`src/sst/ident/mbz.py`)**
  * `time.sleep(1.1)`: レートリミット回避のための固定待機時間（1秒1リクエスト制限の順守）。
  * `limit=20`: リリース検索の最大取得件数。
* **Steam Web API (`src/sst/steam_web_api.py`)**
  * `timeout=15` / `30` / `10`: Store / PICS / Tag の各APIの読み取りタイムアウト秒数。
  * `time.sleep(2.0 + random.random())`: Store APIへのリクエスト間隔（ランダムジッター）。
* **Discord Webhook (`src/sst/notify.py`)**
  * `timeout=10`: Webhook送信（POST）のタイムアウト秒数。

### 2.2 外部コマンド・サブプロセス実行
* **ffmpeg (`src/sst/tagger.py`)**
  * `timeout=600`: 音声変換・タグ書き込み時のデッドロックを防止するためのタイムアウト（10分）。
* **ffprobe (`src/sst/tagger.py`, `src/sst/track_grouper.py`)**
  * `timeout=10`: メタデータ読み出しや時間計測など、即時応答コマンドの制限時間。
* **nvidia-smi (`src/sst/vram_manager.py`)**
  * `timeout=5`: GPU（VRAM）ステータス取得コマンドの制限時間。
