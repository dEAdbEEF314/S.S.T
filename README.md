# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

S.S.T は、Steamで購入したサウンドトラックを自動的に識別し、メタデータを補完してタグ付けを行う、高精度なスタンドアロンCLIツールです。
Steam API、MusicBrainz、およびローカルの埋め込みタグからの情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整理」によって統合します。

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

- 最新のドキュメント整合チェック結果: `report/doc_consistency_check_20260627.md`

### ドキュメント導線
- 正本: `docs/METADATA_SOURCE_SPEC.md`
- コア仕様: `docs/SST.md`, `docs/LOGIC.md`, `docs/TAGGING_RULE.md`
- 運用/環境: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/configuration.md`, `docs/TEST_ENVIRONMENT.md`, `docs/error_handling.md`
- 補助資料: `docs/data_flow_diagram.md`, `docs/api_rate_limit.md`
- バックアップ: `docs/archive/old/`, `docs/archive/v0.1/`

## 🚀 システムアーキテクチャ
S.S.T は **Steam を構造の絶対的な正本とするローカル処理系** です。処理はローカルマシン上で完結し、LLM は必要時のみトラック整列の判断者として使います。

### コア・パイプライン
1. **STEAM 骨格構築**: AppID からアルバム情報とストアトラック一覧を取得し、正規スロットを定義します。
2. **シグナル収集**: ローカル全ファイルから duration、埋め込みタグ、ファイル名情報、AcoustID、ディスク推定を集めます。
3. **ファストトラック判定**: 曲数一致とトラック番号の 1:1 対応が明確なら、LLM を呼ばずに整列を確定します。
4. **LLM アライメント**: あいまいさが残る場合のみ、LLM が各ファイルを STEAM スロットへ割り当てます。
5. **タグ構築と出力**: 変換元は Tier 規則で機械的に選び、ID3v2.3 タグを付与して archive/review に出力します。

## ✨ 主な機能
- **STEAM First**: トラック構造、アルバム構造、タイトル骨格は STEAM を絶対基準とします。
- **Selective LLM**: 整ったアルバムでは LLM をバイパスし、あいまいケースにだけ判断を委譲します。
- **Deterministic Source Selection**: 変換元ファイル選択とタグフォールバックを機械規則で固定します。
- **Slot-wise EMBED Pickup**: 同一スロット内の別フォーマットから APIC や既存コメントを救済できます。
- **Review Isolation**: 確証不足ケースを黙って通さず、review と理由付きで隔離します。

## ⚙️ システムカスタマイズ (System Customization)
S.S.T は `.env` ファイルを通じて、システムの並列性能やAPIの安全性を極限までチューニングできます。

メタデータソースは 6 分類（STEAM / ACOUSTID / MBZ_RELEASE / MBZ_SEARCH / EMBED / LOCAL）で整理され、各フィールドの採用順序は `docs/METADATA_SOURCE_SPEC.md` で固定されています。

### LLM チャンク制御およびAPIレートリミット
LLM はあいまいな整列ケースにだけ使います。主な調整項目は次です。
- **`LLM_OLLAMA_NUM_CTX` / `LLM_OLLAMA_NUM_PREDICT`**: Ollama 利用時のコンテキスト長と出力上限。
- **`LLM_LIMIT_RPM` / `LLM_LIMIT_TPM` / `LLM_LIMIT_RPD`**: クラウド API 利用時の上限制御。
- **`LLM_CLOUD_MAX_TOKENS`**: クラウドモデルの最大出力トークン。
- **`MAX_PARALLEL_ALBUMS`**: アルバム単位の基本並列数。

これらは実行性能を調整するための設定であり、メタデータの採用優先順位そのものは変更しません。詳細は `docs/configuration.md` を参照してください。

### 音声エンコードおよび全体並列制御
- **`MAX_ENCODING_TASKS`**: FFmpegによる音声フォーマット変換を同時にいくつ走らせるかを指定します。ディスクI/OとCPU負荷に直結するため、SSD環境でも `4` 〜 `8` 程度が推奨されます。
- **`MAX_PARALLEL_ALBUMS`**: システム全体で同時に進行するアルバム処理の「基本並行数」です。クラウドAPI利用時は、RPMから自動算出された安全な並行数とこの値を比較し、**大きい方**が採用されます（手動で並行数を強制的に底上げしたい場合に使用します）。Ollama利用時はこの値に関わらず起動時に算出された安全な固定スロット数が優先されます。

## ✅ 確認が取れている実行環境
- **OS**: Linux (Ubuntu 24.04 等)
- **dGPU**: NVIDIA GPU 推奨 (16GB VRAM以上) ※ローカルLLMを使用する場合のみ
- **Software**: 
  - **FFmpeg**: 必須（音声変換用）。必ずOSにインストールしてパスを通してください。
  - **Python**: 3.12 以上 (`uv` での管理を推奨)
  - **Ollama**: ローカルLLM推論用 (オプション)
  - **PICS Bridge API**: Steam 商品情報取得のためにアクセス可能なエンドポイントが必要

## 🛡️ 安全なローカル運用

S.S.T は個人のSteamサウンドトラックを処理するローカルCLIです。Steamライブラリの元ファイルは読み取り専用で扱い、出力先・作業領域・ログ領域を分離してください。Linuxでは、Steamライブラリを読み取り専用マウント（`ro`）で提供する運用を推奨します。S.S.Tは元ファイルを書き換えませんが、読み取り専用マウントは誤操作時の最終的な保護層になります。

通常運用では `.env` の `LOG_LEVEL=INFO`（既定値）を使用します。`--dev` または `LOG_LEVEL=DEBUG` では、診断用ログと `SST_WORKING_DIR` 内の `final_<AppID>_*` / `buffer_<AppID>_*` 中間生成物を保持します。INFO運用では処理完了後に中間生成物を削除します。DEBUG成果物にはプロンプト、応答、ローカルパス、タグ情報が含まれ得るため、共有・バックアップ前に確認してください。

確証不足、未割当ファイル、Steamスロット不一致、重複、必須タグ欠落、FFmpeg変換失敗または音声警告は `review` に隔離されます。Archive前には生成物のファイル数・存在・タグ整合性を検証します。

## 🏗️ セットアップと起動

### 1. インフラの準備と設定
S.S.TはSteamの内部メタデータを取得するため、[steamcmd/api](https://github.com/steamcmd/api) 互換の PICS Bridge API を必要とします。各自の環境に合わせてローカルでホストするか、アクセス可能なサーバーを用意し、`.env` の `STEAM_PICS_BRIDGE_URL` にURLを設定してください。

> **💡 LLMの設定**: LLMサービス（Gemini API、Ollama等のローカル環境、OpenAI互換API）はユーザー各自で用意し、`.env` ファイルにAPIキーやURLを正しく設定してください。
>
> **💡 Ollamaの推奨モデル**: 2026-07 時点の実測では、ローカル推論の推奨モデルは `ornith:9b` です。`qwen35` 系で観測された並列 request 非対応を回避しつつ、`gemma3:1b` より複雑ケースで安定しました。

### 2. S.S.T システムの実行
```bash
# 依存関係のインストール (プロジェクトルートで実行)
uv sync

# アルバム処理の開始 (例: 10件)
./sst --limit 10
```

## 🏷️ タグ表記仕様 (COMM欄)
COMM は次の要素で構築します。
- **書式**: `既存コメント, 親ゲーム名, 親ゲームURL, [タグ1/ タグ2/ ...]`
- **既存コメント**: 同一 STEAM スロット内の全フォーマットから横断検索します。
- **自動調整**: UTF-16 で 2000 バイトを超える場合、末尾タグから削って収めます。

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
- Source of truth: `docs/METADATA_SOURCE_SPEC.md`
- Core specs: `docs/SST.md`, `docs/LOGIC.md`, `docs/TAGGING_RULE.md`
- Operations/Environment: `docs/DEPLOYMENT_GUIDE_jp.md`, `docs/configuration.md`, `docs/TEST_ENVIRONMENT.md`, `docs/error_handling.md`
- Supporting specs: `docs/data_flow_diagram.md`, `docs/api_rate_limit.md`
- Backups only: `docs/archive/old/`, `docs/archive/v0.1/`

## 🚀 System Architecture
S.S.T is a **local processing pipeline with STEAM as the structural source of truth**. The LLM is used only when track alignment is ambiguous.

### Core Pipeline
1. **Build the STEAM skeleton**: Collect album-level metadata and the store track list from the AppID.
2. **Collect local signals**: Read duration, embedded tags, filename hints, AcoustID, and disc hints from every local audio file.
3. **Fast-track decision**: If the local set maps cleanly to STEAM slots, finalize without the LLM.
4. **LLM alignment**: Only ambiguous albums go through slot assignment by the LLM.
5. **Tagging and output**: Select the conversion source deterministically, build ID3v2.3 tags, and write archive/review outputs.

## ✨ Key Features
- **STEAM First**: STEAM defines the canonical album and track structure.
- **Selective LLM usage**: Clean albums bypass the LLM entirely.
- **Deterministic fallback rules**: Source precedence is fixed per field.
- **Slot-wide EMBED pickup**: Artwork and existing comments can be recovered from sibling formats in the same slot.
- **Review isolation**: Ambiguous albums are quarantined with explicit reasons instead of being silently archived.

## ⚙️ System Customization
S.S.T can be deeply tuned for parallel performance and API safety via the `.env` file.

### LLM Chunk Control & API Rate Limits
The LLM is only used for ambiguous alignment cases. The main knobs are:
- **`LLM_OLLAMA_NUM_CTX` / `LLM_OLLAMA_NUM_PREDICT`**: Context and output limits for Ollama.
- **`LLM_LIMIT_RPM` / `LLM_LIMIT_TPM` / `LLM_LIMIT_RPD`**: Rate controls for cloud APIs.
- **`LLM_CLOUD_MAX_TOKENS`**: Maximum output tokens for cloud models.
- **`MAX_PARALLEL_ALBUMS`**: Base album-level concurrency.

These values tune performance and stability only. They do not change source precedence or tagging rules. See `docs/configuration.md` for the authoritative settings guide.

### Audio Encoding & Parallel Limits
- **`MAX_ENCODING_TASKS`**: Concurrent FFmpeg audio conversion processes. Impacts CPU and Disk I/O (4-8 recommended for SSDs).
- **`MAX_PARALLEL_ALBUMS`**: The "base concurrency" for album processing. When using Cloud APIs, the system compares this value with the auto-calculated safe concurrency (based on RPM) and adopts the **larger** one (useful if you want to manually force higher concurrency). When using Ollama, the autonomous slot calculation based on VRAM takes precedence regardless of this value.

## ✅ Verified Environment
- **OS**: Linux (Ubuntu 24.04 or equivalent)
- **dGPU**: NVIDIA GeForce RTX 40-series (16GB VRAM recommended) *Only required for local LLM inference
- **Software**: 
  - **FFmpeg**: Required for audio conversion. Must be installed and accessible in the system PATH.
  - **Python**: 3.12+ (managed with `uv` recommended)
  - **Ollama**: For local LLM inference (optional)
  - **PICS Bridge API**: An accessible endpoint for Steam product metadata

## 🏗️ Setup & Startup

### 1. Starting Infrastructure & Configuration
```bash
# Start Steam PICS Bridge
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
```

> **💡 LLM Setup**: Please provide your own LLM service (Gemini API, Ollama, OpenAI-compatible APIs) and configure the API keys and URLs correctly in your `.env` file.
>
> **💡 Recommended Ollama model**: As of 2026-07, the recommended local Ollama model is `ornith:9b`. In measured SST runs, it avoided the parallel-request limitation observed with `qwen35`-family models and was more stable on complex cases than `gemma3:1b`.

### 2. Running S.S.T
```bash
# Install dependencies (Run at root)
uv sync

# Start processing (e.g., limit 10)
./sst --limit 10
```

## 🏷️ Tagging Specifications (COMM Field)
COMM is built from the existing embedded comment, parent game title, parent game URL, and Steam user tags.
- **Format**: `Existing comment, Parent game title, Parent game URL, [tag1/ tag2/ ...]`
- **Cross-format pickup**: The embedded comment may come from another format assigned to the same STEAM slot.
- **Auto-pruning**: If the value exceeds 2000 bytes in UTF-16, trailing tags are removed one by one.

## ⚠️ Review
- **Isolation**: Ambiguous metadata is preserved as ZIP archives under `output/review/`. Reasoning is provided in `AUDIT_REPORT.html`.
- **Manual correction**: Extract and correct target ZIPs under `output/review/`. Automated ingestion of corrected results is planned as a future feature.

## ❤️ A Final Request
If you find this system useful, **please help someone in need tomorrow, even in a small way.** That is the best way to "pay" for this software.
