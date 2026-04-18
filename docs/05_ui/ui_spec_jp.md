# UI仕様書: S.S.T エンジニアダッシュボード

## 概要
分散型 Steam Soundtrack Tagger (S.S.T) パイプラインを監視するための、モダンでエンジニア中心のダッシュボードです。React と shadcn/ui を使用して構築され、タグ付けプロセスのリアルタイムな可視性を提供します。

## 技術スタック
- **フロントエンド**: React 18 (Vite), TypeScript, Tailwind CSS, shadcn/ui.
- **バックエンド**: FastAPI (Python 3.12).
- **アイコン**: Lucide React.
- **状態管理**: TanStack Query (React Query) によるデータ取得とポーリング。

## 主要機能

### 1. ダッシュボード (Home)
システム状態の視覚的な概要。
- **グローバルメトリクス**:
  - `Scanned`: Steamライブラリで見つかったアルバムの総数 (S3 `ingest/`)。
  - `Processing`: 現在タグ付け実行中のアルバム (Prefect `Running`)。
  - `Archive`: タグ付けが成功したアルバム (S3 `archive/`)。
  - `Review`: 人手による確認が必要なアルバム (S3 `review/`)。
- **システム健全性**: Prefect Server, S3 (SeaweedFS), および LLM (Open-WebUI) への接続ステータス。

### 2. パイプラインモニター (`/pipeline`)
フロー実行のリアルタイム追跡。
- **データテーブル**: `SST-Production-Pipeline` のフロー実行一覧を表示。
- **カラム**: `App ID`, `アルバム名`, `状態` (バッジ), `開始時間`, `経過時間`。
- **状態バッジ**: 
  - `Scheduled`: グレー
  - `Running`: 青 (アニメーション付き)
  - `Completed`: 緑
  - `Failed`: 赤
  - `Cancelled`: 黄色

### 3. LLM 対話ログ (`/llm-logs`)
AI の意思決定プロセスのエンジニア向けビュー。
- **チャット UI**: システムプロンプト、ユーザープロンプト、およびモデルの回答を表示。
- **メタデータ**: モデル名 (例: `llama3.1`)、トークン使用量（利用可能な場合）、およびタイムスタンプを表示。
- **多言語対応**: 日本語の曲名やメタデータ検証結果を文字化けなく完全にレンダリング。

### 4. アーカイブ & レビューエクスプローラー
処理済みファイルの閲覧とダウンロード。
- **リストビュー**: 処理済みアルバムをカード形式またはテーブル形式で表示。
- **ダウンロード**: サーバーサイドでのアルバム一括 ZIP 生成をトリガー。

## デザイン指針
- **テーマ**: 完全なダークモード。IDEのような質感を目指し、`slate` または `zinc` パレットを使用。
- **タイポグラフィ**:
  - メインUI: Inter.
  - アルバムメタデータ: Noto Sans JP (文字化けゼロを保証)。
  - コード/JSON: JetBrains Mono.
- **レスポンシブ**: モバイル対応しつつも、デスクトップでの監視を最優先に最適化。

## 内部 API (バックエンド)
- `GET /api/stats`: 集計カウント。
- `GET /api/pipeline`: Prefect API `/flow_runs/filter` へのプロキシ。
- `GET /api/llm-logs`: S3 から対話 JSON ファイルをリストアップ。
- `GET /api/llm-logs/{log_id}`: 詳細な会話データ。
