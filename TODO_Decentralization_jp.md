# TODO: 分散アーキテクチャへの移行

## 概要
このドキュメントは、現在の `docker-compose` ベースの S.S.T (Steam Soundtrack Tagger) システムを、複数の独立したベアメタルサーバー上で稼働する完全な分散アーキテクチャへ移行するために必要な手順をまとめたものです。

## ノードの役割と配置要件

### 1. サーバー A: Scout ノード（データ取り込み）
- **役割**: ローカルのSteamライブラリをスキャンし、メタデータを抽出してS3へアップロードする。
- **要件**: Steamの `steamapps` ディレクトリにローカルアクセスできること。
- **動作**: cronや手動で起動。S3へのアップロード完了後、CoreノードのPrefect APIへWebhookやAPIコールを送信してワークフローをトリガーする。

### 2. サーバー B: Worker ノード（処理エンジン）
- **役割**: 負荷の高い処理（FFmpegによる音声変換、MusicBrainzからのメタデータ取得、ID3タグ付け、画像加工）を行い、結果をS3へアップロードする。
- **要件**: 高いCPU性能とネットワーク帯域。複数台のサーバーに並べて水平スケール（スケールアウト）可能。
- **動作**: `prefect worker` として常駐起動し、Coreノードのワークプールからタスクを取得（ポーリング）して実行する。Steamライブラリへのアクセスは不要。

### 3. サーバー C: Core & Storage ノード（管理サーバー）
- **役割**: Prefect サーバー（状態管理、UI、タスクキュー）および SeaweedFS（S3互換ストレージ）のホスティング。
- **要件**: サーバー A および サーバー B の両方からアクセス可能なIP（VPNやローカルIP等）を持つこと。
- **動作**: 常時稼働し、システム全体の状態とデータを管理する。

## 必要な実装ステップ

- [ ] **ステップ 1: Worker 実行の分離**
  - `worker/Dockerfile` の起動コマンド (`CMD`) を、ローカルテストの実行からPrefectワーカーの起動 (`uv run prefect worker start --pool "sst-worker-pool"`) に変更する。
  - CoreコンテナからWorkerロジックの直接インポート (`from worker.main import WorkerService`) を廃止する。
- [ ] **ステップ 2: Prefect デプロイメントの作成**
  - `core/src/core/main.py` を更新し、タスクをローカル実行するのではなく `sst-worker-pool` にデプロイ（タスク登録）するように変更する。
- [ ] **ステップ 3: Scout からのトリガー実装**
  - `scout/src/scout/main.py` を更新し、S3へのアップロード完了後に生成されたJSONペイロードを含めて、Prefect サーバー (サーバー C) へ HTTP POST リクエストを送り `sst_main_flow` を開始させる。
- [ ] **ステップ 4: 環境変数の分離**
  - 各ノード専用の `.env.example` テンプレートを作成し、`PREFECT_API_URL` および `S3_ENDPOINT_URL` がサーバー C のアドレスを指すように設定を整備する。
