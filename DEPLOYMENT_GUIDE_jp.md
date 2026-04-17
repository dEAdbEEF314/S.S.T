# S.S.T 分散デプロイガイド (UI 同居版)

このドキュメントでは、本番テスト用にS.S.Tの各コンポーネントを分散デプロイする方法を説明します。**Server A (Windows PC) で UI をホストする構成**です。

## 1. アーキテクチャ概要

- **Server C (中央管理)**: Core (Prefect Server) および S3互換ストレージをホストします。
- **Server B (ワーカー)**: 水平にスケールし、楽曲の特定やタグ付けタスクを処理します。
- **Server A (エッジ/UI)**: **Windows PC**。Steamライブラリをスキャンし、さらに**ユーザーが操作するUI**を提供します。

## 2. 前提条件

- 全てのサーバーに Docker / Docker Compose がインストールされていること（Windows は Docker Desktop + WSL2 推奨）。
- ノード間の疎通確認（Prefect: 4200, S3: 8333, UI: 8000）。

---

## 3. Server C: 中央管理 (Core)

### ステップ 1: 環境設定
`.env.core.example` を `.env.core` にコピーし、S3等の設定を行います。
```bash
cp .env.core.example .env.core
```

### ステップ 2: 起動
```bash
docker-compose -f docker-compose.core.yml up -d
```

---

## 4. Server B: 処理ユニット (Worker)

### ステップ 1: 環境設定
`.env.worker.example` を `.env.worker` にコピーし、**Server C の IP** を指定します。

### ステップ 2: 起動
```bash
docker-compose -f docker-compose.worker.yml up -d
```

---

## 5. Server A: エッジ & UI (Scout & UI)

この PC はあなたのメイン PC (Windows) を想定しています。

### ステップ 1: 環境設定
`.env.scout.example` を `.env.scout` にコピーし、以下を設定します。
- `STEAM_LIBRARY_PATH`: 例 `E:/SteamLibrary` (Docker経由でマウントされます)
- `S3_ENDPOINT_URL`, `PREFECT_API_URL`: **Server C の IP** を指定

### ステップ 2: UI の起動
UI を常駐させます。ブラウザで `http://localhost:8000` を開くことができるようになります。
```bash
docker-compose -f docker-compose.scout.yml up -d ui
```

### ステップ 3: スカウト（スキャン）の実行
スキャンを行いたいタイミングで実行します。
```bash
docker-compose -f docker-compose.scout.yml run --rm scout uv run -m scout.main
```

---

## 6. 動作確認

1. **管理画面**: `http://<SERVER_C_IP>:4200` でワークフローの動きを確認。
2. **S.S.T UI**: `http://localhost:8000` (Server A) で楽曲のブラウズとダウンロードが可能。
