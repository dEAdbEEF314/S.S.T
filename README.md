# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

S.S.T は、Steamで購入したサウンドトラックを自動的に識別し、メタデータを補完してタグ付けを行う、高精度なスタンドアロンCLIツールです。
Steam API、MusicBrainz、およびローカルの埋め込みタグからの情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整理」によって統合します。

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

- 最新のドキュメント整合チェック結果: `report/doc_consistency_check_20260627.md`

### ドキュメント導線
- コア仕様: `docs/SST.md`, `docs/LOGIC.md`, `docs/TAGGING_RULE.md`
- 運用/環境: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/TEST_ENVIRONMENT.md`, `docs/error_handling.md`
- 補助仕様: `docs/Virtual_Album.md`, `docs/data_flow_diagram.md`, `docs/cache_architecture.md`, `docs/api_rate_limit.md`, `docs/discord_integration.md`, `docs/smart_duplicate_resolution.md`, `docs/wsl_path_conversion.md`
- エージェント向け: `docs/AGENT_GUIDE.md`, `docs/VIRTUAL_ALBUM_RULES.md`
- 提案メモ（歴史資料）: `docs/archive/Inference_Optimization.md`, `docs/archive/Parallel_Optimization.md`

## 🚀 システムアーキテクチャ: ハイブリッド・エッジ処理
S.S.T は **ハイブリッド・エッジプロセッサ** です。音声変換やデータ取得などの重い処理はローカルマシン上で実行し、LLM推論はユーザーの好みに応じてクラウドAPI（Gemini等）またはローカル環境（Ollama）を選択して実行します。これにより、環境に応じたパフォーマンスとプライバシーのバランスを実現します。

### コア・パイプライン (Two-Phase Architecture)
1. **スキャン**: Steamライブラリをスキャンし、ローカルのSQLiteデータベースを参照して未処理のアルバムを特定。
2. **Phase 1: Data Gathering & Pre-Fetch (事前一括取得)**:
    - LLMを待たせずに、対象アルバムの音声指紋(`fpcalc`)計算と外部API (AcoustID, MusicBrainz) からのメタデータ取得をマルチスレッドで一括実行し、ローカルDBへキャッシュします。
3. **Phase 2: LLM Consolidation (推論と統合)**:
    - 4つの仮想アルバム (STEAM公式, ローカル実体, 音声指紋, テキスト検索) を構築し、LLMが情報を比較・推論。
    - ユーザー（立法）が定めた優先順位に従い、LLM（司法）が決定を下し、システム（行政）が物理的なクリーンネス（トラック番号除去等）を強制執行。
4. **出力 (Read-Onlyライブラリ保護)**:
    - Steamライブラリ内の実ファイルは絶対に書き換えず、変換やID3v2.3タグ付けを行いながら、直接指定された出力先 (`SST_OUTPUT_DIR`) にZIPアーカイブ等として出力します。

## ✨ 主な機能
- **Two-Phase Pipeline**: ネットワークI/OとLLM推論を完全に分離。APIキャッシュとマルチスレッド・フェッチにより、LLMの待機時間を排除し全体の処理を高速化。
- **Zero-Config Dynamic VRAM Scheduling**: Ollama利用時は自律検出した空きVRAMの80%を上限とする動的セマフォで最適に並行処理（Token Stingy戦略）。外部API時はレートリミットに準拠したスレッドプールへ自動切り替え。また、OllamaのトークナイザーAPIが利用できない環境では、`tiktoken` による高精度なローカル推論へ自動フォールバックしVRAMの計算精度を保ちます。
- **三権分立ロジック**: DJ機材での視認性を重視し、`01. Title` などの Dirty Tags を原則クリーニング（ただし公式名と完全一致する場合は例外として尊重）。
- **インテリジェント・タグ・プルーニング**: ID3v2.3の制限を遵守するため、長すぎるタグを末尾からタグ単位で自動削除。
- **Smart Duplicate Resolution**: LLMが誤認した重複トラックを、ディスク番号や名前ベースの再検索によって自動的に正しいエントリへ再配分。

## ⚙️ システムカスタマイズ (System Customization)
S.S.T は `.env` ファイルを通じて、システムの並列性能やAPIの安全性を極限までチューニングできます。

メタデータソースの優先順位も `.env` で上書きできます。未設定時のフォールバック値は `src/sst/config.py` に集約され、各実装層で共通に参照されます。

### LLM チャンク制御およびAPIレートリミット
APIの頭打ちを防ぎつつ、モデルのスペック限界までコンテキスト長を最大化（One-shot処理化）するための設定群です。
- **`LLM_OLLAMA_NUM_CTX`**: (Ollama専用) モデルに割り当てる最大コンテキスト長（例: Llama 3 8B なら 8192、Qwen 2.5 なら 32768）。この値が大きいほど長大なアルバムを一撃処理できますが、比例してVRAM（KVキャッシュ）を大量消費します。並列実行数を増やしたい場合は意図的に下げる（例: 4096）チューニングが有効です。
- **`LLM_OLLAMA_NUM_PREDICT`**: (Ollama専用) モデルが幻覚や構造破綻を起こさずに長文JSONを出力し続けられる「信頼度の天井」となるトークン数（推奨: 大型モデルなら8192、小型なら4096等）。実際の通信では出力を途切らせないため `-1` (無限) を付与しますが、この設定値がチャンク計算の数学的上限として機能しモデルを保護します。
- **`LLM_LIMIT_RPM` / `LLM_LIMIT_TPM`**: (クラウドAPI専用) ご利用のAPI（無料枠・有料枠等）の「毎分リクエスト数」「毎分トークン数」の上限を正確に指定してください。システムはこれらの値から安全な同時実行数と限界曲数を自動算出します。
- **`LLM_CLOUD_MAX_TOKENS`**: (クラウドAPI専用) 使用するモデルの最大出力トークンを指定します。
- **`LLM_CHUNK_ADAPTIVE`**: (デフォルト `true`)。固定のチャンクサイズ指定を無視し、上記の設定から「エラーを起こさず一撃処理できる限界曲数」を動的算出するマスタースイッチです。
- **`LLM_COHERENCE_THRESHOLD`**: (デフォルト `75`)。アルバムの曲数がこの閾値を超えた場合に、超巨大アルバム専用の「階層型Map-Reduce（Coherence処理）」を自動発動させます。プロンプト上限（Context Window）やVRAM枯渇を防ぐための安全装置です。

### 音声エンコードおよび全体並列制御
- **`MAX_ENCODING_TASKS`**: FFmpegによる音声フォーマット変換を同時にいくつ走らせるかを指定します。ディスクI/OとCPU負荷に直結するため、SSD環境でも `4` 〜 `8` 程度が推奨されます。
- **`MAX_PARALLEL_ALBUMS`**: システム全体で同時に進行するアルバム処理の「基本並行数」です。クラウドAPI利用時は、RPMから自動算出された安全な並行数とこの値を比較し、**大きい方**が採用されます（手動で並行数を強制的に底上げしたい場合に使用します）。Ollama利用時はこの値に関わらずVRAMベースの自律制御が優先されます。

## ✅ 確認が取れている実行環境
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 4000番台推奨 (16GB VRAM以上) ※ローカルLLMを使用する場合のみ
- **Software**: 
  - **FFmpeg**: 必須（音声変換用）。必ずOSにインストールしてパスを通してください。
  - **Ollama**: ローカルLLM推論用 (Native WSL2版 / オプション)
  - **Docker Desktop for Windows**: Steam PICS Bridge API用

## 🏗️ セットアップと起動

### 1. インフラの準備と設定
```bash
# Steam PICS Bridge の起動 (Steam内部DBアクセス用)
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
```

> **💡 LLMの設定**: LLMサービス（Gemini API、Ollama等のローカル環境、OpenAI互換API）はユーザー各自で用意し、`.env` ファイルにAPIキーやURLを正しく設定してください。

### 2. S.S.T システムの実行
```bash
# 依存関係のインストール (プロジェクトルートで実行)
uv sync

# アルバム処理の開始 (例: 10件)
./sst --limit 10
```

## 🏷️ タグ表記仕様 (COMM欄)
DJ機材での視認性と情報の網羅性を両立した形式を採用しています。
- **書式**: `親ゲーム名, [タグ1/ タグ2/ ...], AppID, URL`
- **セパレータ**: タグ区切りには `/ ` を使用。
- **自動調整**: 文字数制限（約2000バイト）を超える場合、`[ ]` 内のタグを後ろからタグ単位で削除して収めます。

## ⚠️ レビュー
- **失敗の隔離**: 確証がないアルバムは `output/review/` 配下へ ZIP で保存。理由は `AUDIT_REPORT.html` に記載。
- **手動修正**: `output/review/` 配下の対象 ZIP を展開してメタデータ修正を行います。修正結果の自動取り込み機能は将来対応です。

## ❤️ 最後に
もし、このシステムがあなたの役に立ち、気に入っていただけたなら、**明日あなたの周りで見かける「誰か困っている人」を、ほんの少しだけ助けてあげてください。** それがこのシステムへの一番の対価です。

---

# S.S.T (Steam Soundtrack Tagger)

S.S.T is a high-precision, standalone CLI tool that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata using LLM-assisted "Factual Metadata Organization."

## 📝 Introduction
This tool was created for personal library organization and is shared as a backup. You are free to use and modify it per `LICENSE.md`.

- Latest documentation consistency check: `report/doc_consistency_check_20260627.md`

### Documentation Map
- Core specs: `docs/SST.md`, `docs/LOGIC.md`, `docs/TAGGING_RULE.md`
- Operations/Environment: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/TEST_ENVIRONMENT.md`, `docs/error_handling.md`
- Supporting specs: `docs/Virtual_Album.md`, `docs/data_flow_diagram.md`, `docs/cache_architecture.md`, `docs/api_rate_limit.md`, `docs/discord_integration.md`, `docs/smart_duplicate_resolution.md`, `docs/wsl_path_conversion.md`
- Agent-facing: `docs/AGENT_GUIDE.md`, `docs/VIRTUAL_ALBUM_RULES.md`
- Proposal notes (historical): `docs/archive/Inference_Optimization.md`, `docs/archive/Parallel_Optimization.md`

## 🚀 System Architecture: Hybrid Edge Processing
S.S.T is a **Hybrid Edge Processor**. Audio conversion and data gathering are performed locally, while LLM inference can be offloaded to cloud APIs (like Gemini) or run locally (via Ollama) depending on your preference for performance or privacy.

### Core Pipeline (Two-Phase Architecture)
1. **Scan**: Identifies unprocessed albums using a local SQLite database.
2. **Phase 1: Data Gathering & Pre-Fetch**:
    - Generates audio fingerprints (`fpcalc`) and fetches metadata from external APIs (AcoustID, MusicBrainz) in parallel, caching the results in a local DB before invoking the LLM.
3. **Phase 2: LLM Consolidation**:
    - Constructs 4 Virtual Albums (STEAM, LOCAL, FINGERPRINT, MBZ_SEARCH) for comparison.
    - LLM (Judiciary) infers titles based on user priority (Legislative), while the System (Executive) enforces physical cleanliness (No Dirty Tags).
4. **Process (Strict Read-Only)**:
    - The original Steam Library is never modified. Audio is converted and strict ID3v2.3 tags are written directly to the output directory (`SST_OUTPUT_DIR`), typically packaged as ZIP archives.

## ✨ Key Features
- **Two-Phase Pipeline**: Separates network I/O and LLM inference. API caching and multi-threaded fetching eliminate LLM idle time.
- **Zero-Config Dynamic VRAM Scheduling**: Optimizes concurrent execution via a dynamic VRAM semaphore capped at 80% of auto-detected free VRAM for Ollama (Token Stingy strategy). Automatically switches to a rate-limited thread pool for external APIs. Additionally, automatically falls back to highly accurate local token estimation using `tiktoken` when Ollama's tokenizer API is unavailable, preserving VRAM calculation precision.
- **Strict Tag Enforcement**: Cleans titles like `01. Title` for maximum visibility on DJ gear (unless it perfectly matches the official title).
- **Smart Duplicate Resolution**: Automatically rectifies track misidentifications using disc numbers and fuzzy matching.
- **Intelligent Tag Pruning**: Automatically removes tags from the end of the list to fit ID3v2.3 size limits.

## ⚙️ System Customization
S.S.T can be deeply tuned for parallel performance and API safety via the `.env` file.

### LLM Chunk Control & API Rate Limits
These settings maximize the One-shot processing context while respecting model stability and preventing 429 (Too Many Requests) errors.
- **`LLM_OLLAMA_NUM_CTX`**: (Ollama only) The maximum context window allocated to the model. Larger values allow processing massive albums in one shot but consume significantly more VRAM (KV cache). You can intentionally lower this (e.g., to 4096) to reduce VRAM footprint and increase parallel concurrency.
- **`LLM_OLLAMA_NUM_PREDICT`**: (Ollama only) The "trust ceiling" of your local model. It defines how many tokens the model can safely generate without hallucinating or breaking the JSON structure (e.g., 8192 for large models, 4096 for smaller ones). While the actual API request uses `-1` (infinite) to prevent cut-offs, this value mathematically limits the dynamic chunk size to protect the model.
- **`LLM_LIMIT_RPM` / `LLM_LIMIT_TPM`**: (Cloud APIs only) Specify your API tier's exact Requests-Per-Minute and Tokens-Per-Minute limits. The system uses these to calculate safe concurrency and dynamic chunk sizes.
- **`LLM_CLOUD_MAX_TOKENS`**: (Cloud APIs only) Maximum output tokens for your model (e.g., 8192 for Gemini 1.5 Pro).
- **`LLM_CHUNK_ADAPTIVE`**: (Default `true`). The master switch that calculates the absolute maximum tracks per request based on the limits above, overriding any fixed chunk size settings.

### Audio Encoding & Parallel Limits
- **`MAX_ENCODING_TASKS`**: Concurrent FFmpeg audio conversion processes. Impacts CPU and Disk I/O (4-8 recommended for SSDs).
- **`MAX_PARALLEL_ALBUMS`**: The "base concurrency" for album processing. When using Cloud APIs, the system compares this value with the auto-calculated safe concurrency (based on RPM) and adopts the **larger** one (useful if you want to manually force higher concurrency). When using Ollama, VRAM-based autonomous control takes precedence regardless of this value.

## ✅ Verified Environment
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 40-series (16GB VRAM recommended) *Only required for local LLM inference
- **Software**: 
  - **FFmpeg**: Required for audio conversion. Must be installed and accessible in the system PATH.
  - **Ollama**: For local LLM inference (Native WSL2 / Optional)
  - **Docker Desktop for Windows**: For Steam PICS Bridge API

## 🏗️ Setup & Startup

### 1. Starting Infrastructure & Configuration
```bash
# Start Steam PICS Bridge
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
```

> **💡 LLM Setup**: Please provide your own LLM service (Gemini API, Ollama, OpenAI-compatible APIs) and configure the API keys and URLs correctly in your `.env` file.

### 2. Running S.S.T
```bash
# Install dependencies (Run at root)
uv sync

# Start processing (e.g., limit 10)
./sst --limit 10
```

## 🏷️ Tagging Specifications (COMM Field)
Optimized for both information density and DJ gear compatibility.
- **Format**: `Album Name, [tag1/ tag2/ ...], AppID, URL`
- **Separator**: Uses `/ ` as the tag delimiter.
- **Auto-Pruning**: If the tag exceeds ID3v2.3 limits (~2000 bytes), community tags are removed from the end of the `[ ]` section one-by-one.

## ⚠️ Review
- **Isolation**: Ambiguous metadata is preserved as ZIP archives under `output/review/`. Reasoning is provided in `AUDIT_REPORT.html`.
- **Manual correction**: Extract and correct target ZIPs under `output/review/`. Automated ingestion of corrected results is planned as a future feature.

## ❤️ A Final Request
If you find this system useful, **please help someone in need tomorrow, even in a small way.** That is the best way to "pay" for this software.
