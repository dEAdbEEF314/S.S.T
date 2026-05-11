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

### 1. Ollama 環境の準備
本システムはメタデータの最終判断に LLM を使用します。
1.  [Ollama](https://ollama.com/) をインストールします。
2.  `Models` ディレクトリにある `SST_Modelfile` を使用してモデルを作成します。
    ```bash
    ollama create sst-model -f SST_Modelfile
    ```

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
    git clone https://github.com/your-repo/s-s-t.git
    cd s-s-t
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

### 1. Ollama Setup
The system uses an LLM for final metadata decisions.
1.  Install [Ollama](https://ollama.com/).
2.  Create the specialized model using the provided `SST_Modelfile`:
    ```bash
    ollama create sst-model -f SST_Modelfile
    ```

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
