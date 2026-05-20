# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

S.S.T は、Steamで購入したサウンドトラックを自動的に識別し、メタデータを補完してタグ付けを行う、高精度なスタンドアロンCLIツールです。
Steam API、MusicBrainz、およびローカルの埋め込みタグからの情報を、LLM（大規模言語モデル）を用いた「事実に基づくメタデータ整理」によって統合します。

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

## 🚀 システムアーキテクチャ: スタンドアロン・エッジ処理
S.S.T は **ローカル完結型エッジプロセッサ** です。音声変換、LLMによる統合、タグ付けを含むすべての重い処理は、Steamライブラリが存在するローカルマシン（WSL2/Windows等）上で実行されます。これにより、ネットワークI/Oを最小限に抑え、プライバシーと制御を最大限に確保します。

### コア・パイプライン
1. **スキャン**: Steamライブラリをスキャンし、ローカルのSQLiteデータベースを参照して処理済みアルバムを特定。
2. **情報補完 (3層APIアーキテクチャ)**:
    - 階層1 (Official Store API): 日本語のアルバム名、公式ジャンル、リリース日。
    - 階層2 (Local PICS Bridge): SteamCMD経由での極めて正確なトラックリスト。
    - 階層3 (MusicBrainz / Embedded): 音楽DBと既存のタグ情報。
3. **統合 (三権分立によるメタデータ評価)**:
    - ユーザー（立法）が定めた優先順位に従い、LLM（司法）が情報を比較・推論し、システム（行政）が物理的なクリーンネス（トラック番号除去等）を強制執行。
4. **処理**: 音声を変換（Lossless -> AIFF, Lossy -> MP3）し、DJ機材互換の厳格な ID3v2.3 タグを書き込み。

## ✨ 主な機能
- **Adaptive LLM Router**: 曲数に応じてモデルとコンテキストサイズを動的に切り替え、巨大なアルバムも安全に処理。
- **三権分立ロジック**: DJ機材での視認性を絶対視し、公式名であっても `01. Title` などの Dirty Tags を強制的にクリーニング。
- **Deterministic Fast-Track**: ソース間で情報が完全に一致している場合、LLMをバイパスして決定論的に高速処理。
- **ローカル状態管理**: SQLiteデータベースを使用してすべての処理履歴を追跡。

## ✅ 確認が取れている実行環境
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 4000番台推奨 (16GB VRAM以上)
- **Software**: Docker Desktop for Windows (LLM 推論および API ブリッジ用)

## 🛠️ セットアップと起動

### 1. インフラ・コンテナの起動
```bash
# 1. Local PICS Bridge (Steam内部DBアクセス用)
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest

# 2. llama.cpp Server (LLM 推論エンジン)
# ※ モデルファイル (.gguf) を Models/blobs/ に配置してから実行してください
docker run -d --name sst-llama-server \
  --gpus all \
  -v $(pwd)/Models/blobs:/models \
  -p 11435:8080 \
  ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m /models/qwen2.5-7b.gguf \
  -c 32768 \
  --n-gpu-layers 99 \
  --parallel 2 \
  --host 0.0.0.0 --port 8080
```

### 2. 専用モデルの作成 (Ollamaを使用する場合)
```bash
ollama create qwen2.5:7b-sst -f Models/SST_Modelfile
```

### 3. S.S.T システムの実行
```bash
# 依存関係のインストール (プロジェクトルートで実行)
uv sync

# アルバム処理の開始 (例: 10件)
./sst --limit 10
```

## ⚠️ レビューと確定
- **失敗の隔離**: 確証がないアルバムは自動的に `output/review/` に隔離。理由は `BASIS_for_CLASSIFICATION.md` に記載。
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

### Core Pipeline
1. **Scan**: Identifies unprocessed albums using a local SQLite database.
2. **Enrich (3-Layer API)**: Fetches data from Official Store API, Local PICS Bridge (Internal DB), and MusicBrainz.
3. **Consolidate (Separation of Powers)**: LLM (Judiciary) infers titles based on user priority (Legislative), while the System (Executive) enforces physical cleanliness (No Dirty Tags).
4. **Process**: Converts audio (Lossless to AIFF, Lossy to MP3) and writes strict ID3v2.3 tags.

## ✨ Key Features
- **Adaptive LLM Router**: Dynamically switches models/context sizes for large albums.
- **Strict Tag Enforcement**: Forcefully cleans titles like `01. Title` for maximum visibility on DJ gear.
- **Deterministic Fast-Track**: Bypasses LLM when sources perfectly align for instant processing.
- **Local State**: Tracks history in SQLite to avoid redundant API calls.

## ✅ Verified Environment
- **OS**: Windows 11 / WSL2 (Ubuntu 24.04)
- **dGPU**: NVIDIA GeForce RTX 40-series (16GB VRAM recommended)
- **Software**: Docker Desktop for Windows

## 🛠️ Setup & Startup

### 1. Starting Infrastructure
```bash
# 1. Local PICS Bridge
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest

# 2. llama.cpp Server
docker run -d --name sst-llama-server \
  --gpus all \
  -v $(pwd)/Models/blobs:/models \
  -p 11435:8080 \
  ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m /models/qwen2.5-7b.gguf \
  -c 32768 \
  --n-gpu-layers 99 \
  --parallel 2 \
  --host 0.0.0.0 --port 8080
```

### 2. Creating Custom Model (Ollama)
```bash
ollama create qwen2.5:7b-sst -f Models/SST_Modelfile
```

### 3. Running S.S.T
```bash
# Install dependencies (Run at root)
uv sync

# Start processing (e.g., limit 10)
./sst --limit 10
```

## ⚠️ Review & Finalization
- **Isolation**: Ambiguous metadata triggers a move to `output/review/`. Reasoning is provided in `BASIS_for_CLASSIFICATION.md`.
- **Finalize**: After manual correction, run `./sst --finalize` to update the database.

## ❤️ A Final Request
If you find this system useful, **please help someone in need tomorrow, even in a small way.** That is the best way to "pay" for this software.
