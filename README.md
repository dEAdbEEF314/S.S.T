
## 📄 README.md

# SST (Steam Soundtrack Tagger)

SST is a distributed system that automatically identifies, enriches, and tags soundtracks purchased on Steam.

This repository currently contains the **documentation-first design** of the system, structured for AI-assisted implementation.

---

# 🚀 Overview

SST performs the following pipeline:

1. Scan Steam library
2. Detect soundtrack files
3. Match with external databases (VGMdb / MusicBrainz)
4. Normalize metadata (LLM-assisted)
5. Write ID3 tags
6. Store processed audio

---

# 🧠 Design Principles

- **Accuracy over speed**
- **Failure isolation (review separation)**
- **Deterministic and retryable processing**
- **Stateless, scalable workers**
- **AI-assisted but rule-governed decisions**

---

# 🏗️ Repository Structure

```

docs/
├── SST.md                  # Core concept & navigation root
│
├── 00_overview/            # High-level understanding
├── 01_spec/                # Strict specifications (I/O, tagging, config)
├── 02_execution/           # Pipeline & runtime behavior
├── 03_ai/                  # LLM / agent behavior definitions
└── 04_infra/               # Infrastructure design

```

---

# 📚 Documentation Guide

Start here:

👉 `docs/SST.md`

Then follow depending on your goal:

### For understanding the system
- `00_overview/README.md`
- `00_overview/architecture.md`

### For implementation
- `01_spec/io_spec.md`
- `02_execution/pipeline.md`
- `02_execution/identification_strategy.md`

### For AI / agent development
- `03_ai/agent_prompt.md`
- `03_ai/llm_strategy.md`

---

# 🤖 AI-Driven Development

This project is designed to be implemented using AI agents.

Each document is:

- Self-contained
- Strictly scoped
- Machine-readable

Agents should:

- Follow specifications strictly
- Avoid guessing
- Route low-confidence results to `review`

---

# 📦 Current Status

- ✅ Architecture defined
- ✅ Specifications defined
- ✅ Execution model defined
- ✅ Core workflow (Prefect 3.x) implemented
- ✅ Scout with Local Caching & Rate Limiting implemented
- ✅ Distributed Worker nodes implemented
- ✅ Web UI for album browsing implemented

# ✨ Key New Features (Decentralized Update)

- **Local Scan Caching**: Scout uses `scout_cache.json` to skip non-soundtrack apps and already-scanned metadata, drastically reducing Steam API calls.
- **Intelligent Rate Limiting**: Automatic 429 (Too Many Requests) detection with exponential backoff (1m, 3m, 5m, 10m intervals).
- **Multi-language Support**: Preferred metadata language (e.g., Japanese) with automatic fallback to English.
- **Standalone UI**: UI can be deployed on the edge (Server A) for direct access to processed files.

---

# 🛠️ Planned Stack

- Python 3.11+
- uv (Mandatory for dependency and virtual environment management)
- **Docker / Docker Compose (Standalone Containerized Architecture)**
- Prefect (workflow orchestration)
- SeaweedFS (S3-compatible storage)
- OpenAI-compatible LLM APIs
- AcoustID / MusicBrainz / VGMdb

---

# ⚠️ Important Notes

- This project prioritizes **correctness over automation rate**
- All failures must be **explicitly logged and isolated**
- No silent fallback is allowed

---

# 📄 License

TBD

---

# 🇯🇵 日本語版

---

# SST (Steam Soundtrack Tagger)

SSTは、Steamで購入したサウンドトラックを自動的に識別・補完・タグ付けする分散処理システムです。

本リポジトリは現在、**AIエージェントによる実装を前提としたドキュメント設計**を提供しています。

---

# 🚀 概要

SSTは以下の処理を行います：

1. Steamライブラリのスキャン
2. サウンドトラックの検出
3. 外部DB（VGMdb / MusicBrainz）との照合
4. メタデータ正規化（LLM使用）
5. ID3タグ書き込み
6. 音源の保存

---

# 🧠 設計思想

- **速度より正確性**
- **失敗の分離（review行き）**
- **決定論的かつリトライ可能**
- **ステートレスでスケーラブル**
- **AI補助だがルール優先**

---

# 🏗️ リポジトリ構成

```

docs/
├── SST.md                  # 中核ドキュメント（入口）
│
├── 00_overview/            # 概要理解
├── 01_spec/                # 厳密仕様
├── 02_execution/           # 実行フロー
├── 03_ai/                  # AI挙動定義
└── 04_infra/               # インフラ設計

```

---

# 📚 ドキュメントの読み方

まずここから：

👉 `docs/SST.md`

目的別：

### 全体理解
- `00_overview/README.md`
- `00_overview/architecture.md`

### 実装
- `01_spec/io_spec.md`
- `02_execution/pipeline.md`
- `02_execution/identification_strategy.md`

### AI開発
- `03_ai/agent_prompt.md`
- `03_ai/llm_strategy.md`

---

# 🤖 AI前提設計

本プロジェクトはAIエージェントによる実装を前提としています。

各ドキュメントは：

- 単一責務
- 機械可読
- 厳密仕様

エージェントの原則：

- 仕様を厳守
- 推測しない
- 低信頼はreviewへ

---

# 📦 現在の状態

- ✅ アーキテクチャ定義済み
- ✅ 仕様定義済み
- ✅ 実行モデル定義済み
- ✅ コアワークフロー（Prefect 3.x）実装済み
- ✅ スカウト（キャッシュ・レート制限機能付き）実装済み
- ✅ 分散ワーカーノード実装済み
- ✅ ブラウズ用Web UI実装済み

# ✨ 主な新機能（分散デプロイ対応）

- **ローカルスキャンキャッシュ**: `scout_cache.json` を使用して非サウンドトラックアプリや取得済みメタデータをスキップ。Steam APIへの負荷を激減させます。
- **インテリジェント・レート制限**: Steam APIの429（過剰アクセス）を検知し、指数関数的バックオフ（1分、3分、5分、10分間隔）で自動待機。
- **多言語対応**: `.env.scout` で指定した言語（日本語等）を優先して取得。失敗時は自動的に英語にフォールバック。
- **独立UIデプロイ**: UIをエッジ（Server A）で実行でき、ブラウザから直接成果物の確認・ダウンロードが可能。

---

# 🛠️ 技術スタック（予定）

- Python 3.11+
- Prefect
- Docker
- SeaweedFS
- OpenAI互換LLM
- AcoustID / MusicBrainz / VGMdb

## 🏗️ 独立インフラストラクチャの構築

S.S.Tシステムは、自身のdocker-composeスタック外で独立して稼働するインフラコンポーネントを前提としています。

### 1. Prefect サーバー（オーケストレーター）
タスクキューの管理とフローの監視を行う中央サーバーです。
```bash
docker run -d --name prefect-server -p 4200:4200 -e PREFECT_SERVER_API_HOST=0.0.0.0 prefecthq/prefect:2-python3.11 prefect server start --host 0.0.0.0
```
`.env` ファイルの `PREFECT_API_URL` を `http://<サーバーのIP>:4200/api` に更新してください。

### 2. SeaweedFS (S3互換ストレージ)
`ingest`、`archive`、`review` 用のファイルストレージです。
SeaweedFS用の `docker-compose.yml` を作成します：
```yaml
version: '3'
services:
  master:
    image: chrislusf/seaweedfs
    ports:
      - 9333:9333
    command: "master"
  volume:
    image: chrislusf/seaweedfs
    ports:
      - 8080:8080
    command: "volume -max=5 -mserver=master:9333 -port=8080"
  s3:
    image: chrislusf/seaweedfs
    ports:
      - 8333:8333
    command: "s3 -mserver=master:9333 -port=8333"
```
`docker-compose up -d` で起動後、`.env` ファイルの `S3_ENDPOINT_URL`（例: `http://<サーバーのIP>:8333`）と認証情報を設定してください。

### 3. LLM サーバー (OpenAI互換)
テキストの正規化に使用します。ローカルモデル（OllamaやvLLMなど）または外部APIを利用可能です。
`.env` ファイルの `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_NAME` を更新してください。

---

# ⚠️ 注意事項

- 自動化率より**正確性優先**
- 失敗は必ず記録・分離
- サイレントフォールバック禁止

---

# 📄 ライセンス

未定
