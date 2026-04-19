# テスト環境仕様書

## 概要
このドキュメントは、S.S.T (Steam Soundtrack Tagger) システムのテストに使用される環境とインフラストラクチャについて記述します。この環境は、Docker とローカルドメイン名でアクセス可能な外部サービスを使用し、分散型の本番環境をシミュレートするように設計されています。

## インフラストラクチャの依存関係
システムは以下の外部サービスに依存しています。これらは Nginx Proxy Manager (NPM) を介してポート番号なしでアクセスできるように管理されています。

- **ストレージ (S3/SeaweedFS)**: `http://swfs-s3.outergods.lan`
  - バケット名: `sst-data`
  - 生ファイルの取り込み (`ingest/`)、処理済みアーカイブ (`archive/`)、レビュー待ちキュー (`review/`)、およびグローバルなレート制限の追跡に使用されます。
- **オーケストレーション (Prefect Server)**: `http://prefect.outergods.lan/api`
  - Core および Worker フローの実行を管理します。
  - Core と Worker は Docker コンテナ内で「常駐型 (served)」デプロイメントとして動作します。
- **AI / LLM**: `https://generativelanguage.googleapis.com/v1beta/openai` (Gemini) またはローカルの Ollama。
  - 曲名やアーティスト名の正規化に使用されます。
  - レート制限 (RPM/TPM/RPD) は厳格に適用され、グローバルに追跡されます。

## コンポーネント構成
テストは、それぞれ専用の設定ファイルを持つ複数の専門ノード（コンテナ）で実行されます。

### 1. Scout ノード (ローカル CLI またはコンテナ)
- **役割**: ローカルの Steam ライブラリをスキャンし、ファイルを S3 にアップロードして、Prefect パイプラインをトリガーします。
- **設定**: `.env.scout`
- **主要コマンド**: `cd scout && uv run -m scout.main --limit 5`

### 2. Core サービス (Docker)
- **役割**: Scout からトリガーを受け取り、Prefect デプロイメントを介して利用可能な Worker に処理タスクを委譲します。
- **コンテナ名**: `sst-core`
- **設定**: `.env.core`

### 3. Worker ノード (Docker)
- **役割**: S3 から音源をダウンロードし、メタデータを抽出、LLM による正規化、フォーマット変換 (AIFF/MP3)、タグ付けを行い、結果をアップロードします。
- **コンテナ名**: `sst-worker`
- **設定**: `.env.worker`

### 4. UI ダッシュボード (Docker)
- **役割**: パイプラインのリアルタイム監視、メタデータのインスペクション、一括削除、および ZIP ダウンロードを提供します。
- **URL**: `http://localhost:8000`
- **設定**: `.env.ui`

## テストのデータフロー
1. **取り込み (Ingest)**: Scout が `/mnt/d/SteamLibrary` をスキャン -> S3 の `ingest/{appid}/` にアップロード。
2. **トリガー**: Scout が Prefect API を呼び出し -> `SST-Production-Pipeline` を開始。
3. **委譲**: Core フローが `sst-worker-flow/sst-worker-deployment` を呼び出し。
4. **処理**: Worker が `format_spec.md` に従ってファイルを処理 -> S3 の `archive/` (成功) または `review/` (要手動確認) にアップロード。
5. **検証**: ユーザーが Web UI を通じて進捗を監視し、処理済みの ZIP をダウンロード。

## Act-7 本番テスト環境のセットアップ
`act-7` ブランチ/リポジトリを使用して本番テストを実行するには、以下の手順に従ってください。

### 1. 環境の準備
`act-7` リポジトリをターゲットディレクトリにプルします。ディレクトリ構造が入れ子（例：`/home/sexyroot/src/S.S.T/S.S.T/`）にならないよう、実行ディレクトリに注意してください。

```bash
mkdir -p /home/sexyroot/src/S.S.T
cd /home/sexyroot/src/S.S.T
# ディレクトリがまだ git リポジトリでない場合:
git clone <repository_url> .
git checkout act-7
# すでにリポジトリである場合:
git pull origin act-7
```

### 2. 設定の同期
ワークスペースから本番テスト環境へ環境設定ファイルをコピーします。

```bash
# ワークスペースのルートから実行:
cp .env.core .env.scout .env.ui .env.worker /home/sexyroot/src/S.S.T/
```

### 3. テストの実行
プロジェクトで定義されている本番テストを実行します。
```bash
cd /home/sexyroot/src/S.S.T
python3 run_production_test.py
```
結果については `scout_error.txt` および `scout_debug.txt` を確認してください。
