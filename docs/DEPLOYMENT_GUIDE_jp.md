# S.S.T スタンドアロン・デプロイガイド (Ultimate Data Mode)

このドキュメントでは、S.S.T をローカル環境（WSL2 + Windows）で最大限のパフォーマンスと精度で動作させるためのセットアップ方法を説明します。

## 1. アーキテクチャ概要

現在の S.S.T は、複雑なサーバー構成を必要としない **スタンドアロン CLI ツール** です。
情報の最大化と Cloudflare 制限の回避のため、以下の 2 つを併用する「究極データ取得モード」を推奨します。

- **S.S.T 本体 (WSL2)**: Python 3.12 + `uv` で動作するメインプログラム。
- **PICS Bridge (Local Docker)**: Steam 内部データベースから直接情報を引き出すためのローカルブリッジ。

## 2. 前提条件

- **WSL2 (Ubuntu等)**: Python 3.12 および `uv` がインストールされていること。
- **Docker Desktop**: Windows 側でインストールされ、WSL2 連携が有効であること。
- **Steam Web API Key**: [こちら](https://steamcommunity.com/dev/apikey)から取得してください。

---

## 3. ステップ 1: インフラの起動

### 3.1 PICS Bridge (Docker)
外部のキャッシュサーバーを介さず、自分の PC から直接 Steam データを取得するために、以下のコマンドをターミナルで実行してください。

```bash
docker run --name sst-pics-bridge -d -p 8080:8000 --restart unless-stopped steamcmd/api:latest
```



## 4. ステップ 2: S.S.T の環境設定 (.env)

プロジェクト直下の `.env` ファイルに、取得したキーや設定を記述します。

```bash
# Steam Web API Key (必須)
STEAM_WEB_API_KEY=あなたのAPIキー

# PICS Bridge URL (デフォルトで http://localhost:8080/v1/info/)
STEAM_PICS_BRIDGE_URL=http://localhost:8080/v1/info/

# LLM設定 (各自で用意したサービスを設定)
LLM_BACKEND=GEMINI
LLM_BASE_URL=https://generativelanguage.googleapis.com
LLM_API_KEY=your_api_key

# Steam dynamicstore クッキー (任意: 所有権チェック用)
# ブラウザのデベロッパーツールで store.steampowered.com の steamLoginSecure の値をコピー
STEAM_LOGIN_SECURE=あなたのセキュアクッキー
```

---

## 5. ステップ 3: 実行

初回実行時、または大規模な処理を開始する際は、以下のコマンドを使用します。

### 依存関係の同期 (初回のみ)
```bash
uv sync
```

### 全件処理の実行
```bash
./sst --all
```

- **進捗確認**: 別のターミナルで `./sst --tail` を実行すると、リアルタイムに詳細ログを監視できます。
- **デバッグ**: `./sst --appid <ID> --dev` を使用すると、特定の AppID に対して詳細なデバッグ情報を出力します。

---

## 6. メンテナンス

- **DBのリセット**: `./sst --delete-db` （3 段階の確認が入ります）
- **レビューの確定**: 人間が MP3tag 等で修正した後、`./sst --finalize` を実行して DB を更新します。
