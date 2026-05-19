# S.S.T (Steam Soundtrack Tagger)
[English version follows the Japanese version]

## 📝 はじめに
このシステムは、作者が自分自身の音楽ライブラリを整理するために作成したツールを、バックアップとしてGitHubに公開しているものです。`LICENSE.md` の内容に従う限り、どなたでも自由に使用・改変いただけます。

## ✅ 確認が取れている実行環境
以下の環境にて正常な動作および性能を確認しています。
- **OS**: Windows 11
- **CPU**: Core i9-14900HX
- **Memory**: 64GB
- **dGPU**: NVIDIA GeForce RTX 4090 Laptop (16GB)
- **Platform**: WSL2 + Ubuntu 24.04
- **Software**: Docker Desktop for Windows (LLM 推論および API ブリッジ用)

**⚠️ プロジェクトのドキュメントについて**
プロジェクトの最新の機能、アーキテクチャ（三権分立、Adaptive Routingなど）、セットアップ手順の詳細については、以下のメインドキュメントを参照してください。

- 🇯Ｐ 日本語ドキュメント: [README_jp.md](./README_jp.md)
- 🇬🇧 English Documentation: [README_en.md](./README_en.md)
- 🧠 メタデータ判定ロジックの詳細: [docs/LOGIC.md](./docs/LOGIC.md)

## 🚀 システムの起動準備 (Setup & Startup)

S.S.Tをフル機能で動作させるには、推論エンジン（LLM）と情報ソース（PICS Bridge）の2つのコンテナを起動する必要があります。

### 1. インフラ・コンテナの起動
以下のコマンドで、メタデータ取得ブリッジと LLM サーバーを起動します。

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
`sst-tuner` で最適化された推論を行うために、専用の Modelfile からモデルを作成します。

```bash
# S.S.T 専用チューニングモデルの作成
ollama create qwen2.5:7b-sst -f Models/SST_Modelfile
```

### 3. S.S.T システムの実行
環境が整ったら、以下のコマンドでアーカイブ処理を開始します。

```bash
# 依存関係のインストール (初回のみ)
cd scout && uv sync

# 10件の実戦テスト実行
uv run -m scout.main --limit 10 --force
```

## ❤️ 最後に
もし、このシステムがあなたの役に立ち、気に入っていただけたなら、**明日あなたの周りで見かける「誰か困っている人」を、ほんの少しだけ助けてあげてください。**

道案内をする、重い荷物を持ってあげる、あるいはちょっとしたお礼を言う。どんなに些細なことでも構いません。それがこのシステムへの一番の対価です。

---

# S.S.T (Steam Soundtrack Tagger)

## 📝 Introduction
This system is a tool I created for my personal music library organization, hosted here on GitHub as a backup. You are free to use and modify it as long as you comply with the terms in `LICENSE.md`.

## ✅ Verified Execution Environment
The system has been verified to work optimally in the following environment:
- **OS**: Windows 11
- **CPU**: Core i9-14900HX
- **Memory**: 64GB
- **dGPU**: NVIDIA GeForce RTX 4090 Laptop (16GB VRAM)
- **Platform**: WSL2 + Ubuntu 24.04
- **Software**: Docker Desktop for Windows (for LLM backend and API bridge)

**⚠️ Project Documentation**
For the latest features, architecture details (Separation of Powers, Adaptive Routing, etc.), and complete setup instructions, please refer to the main documentation files:

- 🇯Ｐ Japanese Documentation: [README_jp.md](./README_jp.md)
- 🇬🇧 English Documentation: [README_en.md](./README_en.md)
- 🧠 Detailed Metadata Logic: [docs/LOGIC.md](./docs/LOGIC.md)

## 🚀 Setup & Startup

To run S.S.T with full functionality, you need to start two containers: the inference engine (LLM) and the information source (PICS Bridge).

### 1. Starting Infrastructure Containers
Use the following commands to start the metadata bridge and the LLM server.

```bash
# 1. Local PICS Bridge (For Steam internal DB access)
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest

# 2. llama.cpp Server (LLM Inference Engine)
# * Place your model file (.gguf) in Models/blobs/ before running
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

### 2. Creating a Custom Model (When using Ollama)
To perform optimized inference with `sst-tuner`, create a model from the specialized Modelfile.

```bash
# Create the S.S.T-tuned model
ollama create qwen2.5:7b-sst -f Models/SST_Modelfile
```

### 3. Running S.S.T System
Once the environment is ready, start the archival process with the following commands:

```bash
# Install dependencies (First time only)
cd scout && uv sync

# Run 10-item production test
uv run -m scout.main --limit 10 --force
```

## ❤️ A Final Request
If you find this system useful and enjoy using it, **please help someone in need tomorrow, even in a small way.**

Giving directions, helping someone carry something heavy, or simply saying a kind word—no matter how trivial it seems, that would be the best way to "pay" for this software.
