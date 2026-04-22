# S.S.T ドキュメント・リストおよび実装整合性レポート

このドキュメントは、ワークスペース内の既存ドキュメントの全体像と、実際のコード実装との整合性を評価したものです。

## 📊 ドキュメント一覧

### 1. コア・全体概要
| ファイルパス | 言語 | 状態 | 目的 |
| :--- | :--- | :--- | :--- |
| `README.md` | EN/JP | **正本** | 現在の「Standalone Edge Model（ローカル完結型）」の主要な情報源。 |
| `docs/00_overview/architecture.md` | EN/JP | **古い** | 初期の分散型（Prefect/Worker）設計を記述。現状と乖離。 |
| `docs/IMPLEMENTATION_PLAN.md` | EN | **進行中** | ロードマップ（Phase 5まで完了、Phase 6はスキップ/再定義）。 |
| `AGENT_GUIDE.md` | EN/JP | **正本** | AIエージェントのためのワークフローガイドライン。 |

### 2. 技術仕様書
| ファイルパス | 言語 | 状態 | 目的 |
| :--- | :--- | :--- | :--- |
| `docs/01_spec/tagging_spec.md` | EN/JP | **有効** | ID3タグおよびアートワーク処理のルール。 |
| `docs/01_spec/format_spec.md` | EN | **有効** | 音声変換制約（AIFF/MP3）。 |
| `docs/03_ai/llm_strategy.md` | EN/JP | **正本** | LLMを用いたメタデータ統合ロジック。 |
| `docs/schemas/*.json` | JSON | **有効** | データ構造の定義（スタンドアロン版でも一部参照）。 |

### 3. 実行・パイプライン
| ファイルパス | 言語 | 状態 | 目的 |
| :--- | :--- | :--- | :--- |
| `docs/02_execution/pipeline.md` | EN/JP | **古い** | S3を介した分散処理フローを記述。現状と乖離。 |
| `docs/02_execution/state_machine.md`| EN | **一部有効** | 状態遷移の概念は有効だが、オーケストレーションが異なる。 |

---

## 🔍 主な相違点 (コード vs ドキュメント)

### 1. 集中型 vs 分散型
- **ドキュメントの記述**: `Scout` がスキャンし、`Core` (Prefect) が制御し、`Worker` が処理する分散システム。
- **実際の実装**: `scout/main.py` がスキャン、LLM統合、変換、タグ付けのすべてを単一のパイプラインで実行。
- **影響**: `core/` ディレクトリは現在空です。「Worker」のロジックは `scout/src/scout/processor.py` に統合されています。

### 2. データフロー
- **ドキュメントの記述**: ローカル -> S3 (Ingest) -> Worker -> S3 (Archive)。
- **実際の実装**: ローカルスキャン -> ローカル処理 (LLM/FFmpeg) -> S3アップロードおよびローカルZIP出力。
- **影響**: S3 (SeaweedFS) は中間バッファではなく、成果物の保存およびUI表示用のデータソースとして利用されています。

### 3. 実装ロードマップ
- **現在のステータス**: `IMPLEMENTATION_PLAN.md` によれば、プロジェクトは Phase 5 (LLM Integration) にあります。Phase 6 (Orchestration/Prefect) は、ローカル実行を最適化するためにスタンドアロンモデルが優先され、スキップまたは再定義された状態です。

---

## 💡 推奨事項

1.  **アーキテクチャ図の更新**: `docs/00_overview/architecture.md` を、現在の「Standalone Edge Model」を反映した内容に修正する必要があります。
2.  **パイプライン仕様の同期**: `docs/02_execution/pipeline.md` を、現在の同期的なローカルフローに合わせて更新してください。
3.  **coreディレクトリの扱い**: スタンドアロンモデルを継続する場合は、共有ユーティリティを配置するか、ディレクトリを削除/リネームすることを検討してください。
4.  **タグ付けの整合性保持**: `scout/tagger.py` が、今後追加される機能（Parent Gameメタデータ等）においても `tagging_spec.md` を厳密に遵守し続けるよう注意してください。
