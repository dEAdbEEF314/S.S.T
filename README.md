# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

S.S.T は、Steamで購入したサウンドトラックを自動的に識別し、メタデータを補完してタグ付けを行う、高精度なスタンドアロンCLIツールです。
Steam API、MusicBrainz、およびローカルの埋め込みタグからの情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整理」によって統合します。

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

## 🚀 システムアーキテクチャ: スタンドアロン・エッジ処理
S.S.T は **ローカル完結型エッジプロセッサ** です。音声変換、LLMによる統合、タグ付けを含むすべての重い処理は、Steamライブラリが存在するローカルマシン（WSL2/Windows等）上で実行されます。これにより、ネットワークI/Oを最小限に抑え、プライバシーと制御を最大限に確保します。

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
- **Tier-based Concurrency**: アルバムの曲数規模に応じて並列処理数（スレッド）を自動調整し、安定したリソース管理を実現。
- **三権分立ロジック**: DJ機材での視認性を重視し、`01. Title` などの Dirty Tags を原則クリーニング（ただし公式名と完全一致する場合は例外として尊重）。
- **インテリジェント・タグ・プルーニング**: ID3v2.3の制限を遵守するため、長すぎるタグを末尾からタグ単位で自動削除。
- **Smart Duplicate Resolution**: LLMが誤認した重複トラックを、ディスク番号や名前ベースの再検索によって自動的に正しいエントリへ再配分。
- **Maintenance ツールキット**: 大規模テストの結果分析、DB整合性チェックなどの保守用スクリプトを `Maintenance/` ディレクトリに集約。

## ✅ 確認が取れている実行環境
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 4000番台推奨 (16GB VRAM以上)
- **Software**: 
  - **Ollama**: ローカルLLM推論用 (Native WSL2版)
  - **Docker Desktop for Windows**: Steam PICS Bridge API用

## 🏗️ セットアップと起動

### 1. インフラの準備
```bash
# 1. Steam PICS Bridge の起動 (Steam内部DBアクセス用)
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest

# 2. ローカルLLM環境の構築 (Ollama + 専用モデル)
# まず、Ollamaサーバーが起動している必要があります。
# ※ WSL2でsystemdが有効でない場合は、別のターミナルで `ollama serve` を実行しておいてください。
# 以下のスクリプトがモデルのプルを一括で行います。
chmod +x Models/LLM_setup.sh
./Models/LLM_setup.sh
```

> **💡 おすすめ設定**: WSL2 で `systemd` を有効化し、`/etc/systemd/system/ollama.service.d/override.conf` に `Environment="OLLAMA_KV_CACHE_TYPE=q4_0"` を設定すると、OS起動時にVRAM消費を抑えた状態でLLMが自動待機する最強の環境になります。

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

## ⚠️ レビューと確定
- **失敗の隔離**: 確証がないアルバムは自動的に `output/review/` に隔離。理由は `AUDIT_REPORT.html` に記載。
- **Finalize**: 手動修正後、`./sst --finalize` を実行してDBを更新。

## ❤️ 最後に
もし、このシステムがあなたの役に立ち、気に入っていただけたなら、**明日あなたの周りで見かける「誰か困っている人」を、ほんの少しだけ助けてあげてください。** それがこのシステムへの一番の対価です。

---

# S.S.T (Steam Soundtrack Tagger)

S.S.T is a high-precision, standalone CLI tool that automatically identifies, enriches, and tags soundtracks purchased on Steam. It consolidates metadata using LLM-assisted "Factual Metadata Organization."

## 📝 Introduction
This tool was created for personal library organization and is shared as a backup. You are free to use and modify it per `LICENSE.md`.

## 🚀 System Architecture: Standalone Edge Processing
S.S.T is a **Local-only Edge Processor**. All heavy lifting—including audio conversion, LLM consolidation, and tagging—is performed locally on your machine (WSL2/Windows).

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
- **Tier-based Concurrency**: Automatically adjusts parallel processing threads based on album track count for stable resource management.
- **Strict Tag Enforcement**: Cleans titles like `01. Title` for maximum visibility on DJ gear (unless it perfectly matches the official title).
- **Smart Duplicate Resolution**: Automatically rectifies track misidentifications using disc numbers and fuzzy matching.
- **Intelligent Tag Pruning**: Automatically removes tags from the end of the list to fit ID3v2.3 size limits.

## ✅ Verified Environment
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 40-series (16GB VRAM recommended)
- **Software**: 
  - **Ollama**: For local LLM inference (Native WSL2)
  - **Docker Desktop for Windows**: For Steam PICS Bridge API

## 🏗️ Setup & Startup

### 1. Starting Infrastructure
```bash
# 1. Start Steam PICS Bridge
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest

# 2. Setup Local LLM Environment (Ollama + Custom Models)
# Note: Ensure the Ollama server is running first. If systemd is not enabled in WSL2, 
# run `ollama serve` in a separate terminal before executing the setup script.
# This script pulls base models.
chmod +x Models/LLM_setup.sh
./Models/LLM_setup.sh
```

> **💡 Pro Tip**: Enable `systemd` in WSL2 and add `Environment="OLLAMA_KV_CACHE_TYPE=q4_0"` to `/etc/systemd/system/ollama.service.d/override.conf`. This ensures the LLM is always ready upon boot while significantly reducing idle VRAM usage.

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

## ⚠️ Review & Finalization
- **Isolation**: Ambiguous metadata triggers a move to `output/review/`. Reasoning is provided in `AUDIT_REPORT.html`.
- **Finalize**: After manual correction, run `./sst --finalize` to update the database.

## ❤️ A Final Request
If you find this system useful, **please help someone in need tomorrow, even in a small way.** That is the best way to "pay" for this software.
