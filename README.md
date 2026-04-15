
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
- 🔄 Implementation in progress

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
- 🔄 実装中

---

# 🛠️ 技術スタック（予定）

- Python 3.11+
- Prefect
- Docker
- SeaweedFS
- OpenAI互換LLM
- AcoustID / MusicBrainz / VGMdb

---

# ⚠️ 注意事項

- 自動化率より**正確性優先**
- 失敗は必ず記録・分離
- サイレントフォールバック禁止

---

# 📄 ライセンス

未定
