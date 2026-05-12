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
    - NVIDIA-SMI: 595.71.01
    - Driver Version: 596.36
    - CUDA Version: 13.2
- **Platform**: WSL2 + Ubuntu 24.04
- **Software**: Ollama, Docker Desktop for Windows

## 🎯 システムの目的
S.S.T は、Steam で配信されているサウンドトラックを高精度に識別し、詳細なメタデータ（タグ情報）を付与するためのスタンドアロン CLI ツールです。
*   **絶対的信頼**: MusicBrainz、Steam PICS、公式 Web API を統合した 3 層構造により、人間が一切確認せずにライブラリに追加できるレベルの「100% 信頼できるアーカイブ」を自動生成することを目標としています。
*   **DJ機材互換**: 現場の DJ 機材での利用を想定し、ID3v2.3 形式の強制やタグのサイズ調整を自動で行います。

## 🚀 インストール方法

1.  **リポジトリのクローン**:
    ```bash
    git clone https://github.com/dEAdbEEF314/S.S.T.git
    cd S.S.T
    ```
2.  **依存関係のセットアップ (WSL2 推奨)**:
    Python 3.12 以上と `uv` が必要です。
    ```bash
    cd scout
    uv sync
    ```
3.  **環境設定**:
    `.env.example` を `.env` にコピーし、必要なキーを設定してください。
    *   `STEAM_WEB_API_KEY`: [Steam公式](https://steamcommunity.com/dev/apikey)から取得。
    *   `LLM_API_KEY`: Gemini 等を使用する場合に必要。

## ⚙️ 使用前の準備

### 1. LLM 推論環境の準備 (Docker llama-server 推奨)
本システムはメタデータの最終判断に LLM を使用します。以前は Ollama を推奨していましたが、16GB VRAM 環境における「4096 トークンのコンテキスト制限」を回避するため、現在は **Docker を用いた公式 `llama-server` (llama.cpp) の利用を強く推奨** しています。これにより 32K 以上の長大なコンテキストを GPU 完結で処理でき、巨大なサウンドトラックの処理精度が飛躍的に向上します。

1.  Ollama をモデルダウンローダーとして使用し、目的のモデル（例: `qwen2.5:7b-instruct`）を Pull します。
2.  ダウンロードされた GGUF ブロブ（`/usr/share/ollama/.ollama/models/blobs/` 内）をプロジェクトの `Models/blobs` にコピーします。
3.  以下の Docker コマンドで CUDA 対応の推論サーバーを起動します：
    ```bash
    docker run -d --name sst-llama-server --gpus all \
      -v $(pwd)/Models/blobs:/models -p 11435:8080 \
      ghcr.io/ggml-org/llama.cpp:server-cuda \
      -m /models/qwen2.5-7b.gguf -c 32768 \
      --n-gpu-layers 99 --parallel 2 --host 0.0.0.0 --port 8080
    ```
4. `.env` の `LLM_BACKEND` を `OPENAI_COMPATIBLE` に設定し、URL を `http://localhost:11435/v1` に指定します。

### 2. Docker Desktop の準備
Steam 内部データベースから直接情報を引き出すための PICS Bridge を起動する必要があります。
1.  Docker Desktop をインストールし、起動しておきます。
2.  以下のコマンドでローカルブリッジコンテナを起動します。このコンテナは、外部のキャッシュサーバー（api.steamcmd.net）に対する Cloudflare の制限を回避するために不可欠です。
    ```bash
    docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
    ```
    *   `-p 8080:8000`: ホストの 8080 ポートをコンテナの 8000 ポートに繋ぎます。
    *   `--restart unless-stopped`: PC 起動時などに自動でコンテナを再開させます。

## 📖 使い方

メインスクリプト `./sst` を使用します。

*   **全件処理**: `./sst --all`
*   **件数制限実行**: `./sst -n 10`
*   **特定のアプリを処理**: `./sst --appid <AppID>`
*   **レビューの確定**: `./sst --finalize` (MP3tag等での手動修正をDBに反映)

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
    - NVIDIA-SMI: 595.71.01
    - Driver Version: 596.36
    - CUDA Version: 13.2
- **Platform**: WSL2 + Ubuntu 22.04+
- **Software**: Ollama, Docker Desktop for Windows

## 🎯 Purpose
S.S.T is a standalone CLI tool designed to identify Steam soundtracks with high precision and enrich them with detailed metadata.
*   **Absolute Trust**: Using a 3-tier API architecture (MusicBrainz, Steam PICS, and Official Web APIs), it automates the creation of "100% reliable archives" that can be added to your library without manual verification.
*   **Hardware Compatibility**: Specifically designed for DJ equipment, it strictly enforces ID3v2.3 and automatically manages tag size constraints.

## 🚀 Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/dEAdbEEF314/S.S.T.git
    cd S.S.T
    ```
2.  **Setup Dependencies (WSL2 Recommended)**:
    Requires Python 3.12+ and `uv`.
    ```bash
    cd scout
    uv sync
    ```
3.  **Configure Environment**:
    Copy `.env.example` to `.env` and fill in the required keys:
    *   `STEAM_WEB_API_KEY`: Get it from [Steam Community](https://steamcommunity.com/dev/apikey).
    *   `LLM_API_KEY`: Required if using external backends like Gemini.

## ⚙️ Prerequisites

### 1. LLM Inference Setup (Docker llama-server Recommended)
The system uses an LLM for final metadata decisions. While Ollama was previously recommended, to bypass the hardcoded 4096-token context limit on 16GB VRAM GPUs, we now **strongly recommend using the official `llama-server` (llama.cpp) via Docker**. This allows processing massive soundtracks with 32K+ context entirely within the GPU, drastically improving accuracy.

1.  Use Ollama as a model downloader to pull the target model (e.g., `qwen2.5:7b-instruct`).
2.  Copy the downloaded GGUF blob (from `/usr/share/ollama/.ollama/models/blobs/`) to the project's `Models/blobs` directory.
3.  Start the CUDA-enabled inference server using the following Docker command:
    ```bash
    docker run -d --name sst-llama-server --gpus all \
      -v $(pwd)/Models/blobs:/models -p 11435:8080 \
      ghcr.io/ggml-org/llama.cpp:server-cuda \
      -m /models/qwen2.5-7b.gguf -c 32768 \
      --n-gpu-layers 99 --parallel 2 --host 0.0.0.0 --port 8080
    ```
4. Configure your `.env` by setting `LLM_BACKEND` to `OPENAI_COMPATIBLE` and the URL to `http://localhost:11435/v1`.

### 2. Docker Desktop Setup
A local PICS Bridge is required to pull data directly from Steam's internal database. This avoids Cloudflare restrictions associated with public cache servers.
1.  Ensure Docker Desktop is installed and running.
2.  Start the local bridge container using the following command:
    ```bash
    docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
    ```
    *   `-p 8080:8000`: Maps host port 8080 to container port 8000.
    *   `--restart unless-stopped`: Ensures the container restarts automatically on boot or if it crashes.

## 📖 Usage

Use the main launcher script `./sst`:

*   **Process All**: `./sst --all`
*   **Limited Run**: `./sst -n 10`
*   **Process Specific App**: `./sst --appid <AppID>`
*   **Finalize Review**: `./sst --finalize` (Ingests manual corrections from tools like MP3tag into the DB)

## ❤️ A Final Request
If you find this system useful and enjoy using it, **please help someone in need tomorrow, even in a small way.**

Giving directions, helping someone carry something heavy, or simply saying a kind word—no matter how trivial it seems, that would be the best way to "pay" for this software.
