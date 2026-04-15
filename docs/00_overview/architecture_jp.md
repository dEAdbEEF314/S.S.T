# アーキテクチャ

## コンポーネント

- **Scout Container**: ローカルのSteamライブラリをスキャンし、ingest（取り込み用）ストレージにアップロードします。
- **Core Container (Prefect)**: ワークフロー、状態管理、およびリトライを制御します。
- **Worker Containers**: 実際の識別、タグ付け、および変換タスクを実行します。
- **LLM Node (Containerized API)**: メタデータの正規化サービスを提供します。
- **Storage (SeaweedFS/S3)**: 独立したS3互換のストレージサービスです。

---

## フロー

Scout Container → ingest → Worker Container → archive/review

---

## 説明

### Scout Container
- Steamライブラリのスキャン（ローカルファイルシステムへのアクセスが必要）
- ACFファイルの解析
- サウンドトラックファイルの収集
- ingestストレージへのアップロード

### Core Container
- Prefectによるオーケストレーションの実行
- 状態管理のハンドリング
- リトライとスケジューリングの制御
- Workerコンテナの起動・管理

### Worker Containers
- ステートレスで個別にスケーラブルな処理ユニット
- 識別、タグ付け、変換を実行
- エフェメラル（一時的）または永続的なコンテナとして動作

### LLM Node
- OpenAI互換のAPI（ローカルコンテナまたは外部サービス）
- タイトルの正規化と検証を担当

### ストレージ (SeaweedFS)
- S3互換のオブジェクトストレージ
- ingest、archive、review、processedのデータを保持
