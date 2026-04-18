# フロントエンド実装仕様書: SST ダッシュボード

## 概要
S.S.T ダッシュボードの React ベースのフロントエンド構築に関する詳細計画です。フロントエンドは `ui/frontend/` に配置され、FastAPI バックエンドによって配信されます。

## 技術スタック
- **フレームワーク**: React 18 (Vite)
- **言語**: TypeScript
- **スタイリング**: Tailwind CSS
- **UI コンポーネント**: shadcn/ui (Radix UI ベース)
- **アイコン**: Lucide React
- **データ取得**: TanStack Query (React Query) v5
- **ルーティング**: React Router DOM v6

## ディレクトリ構造
```
ui/frontend/
├── src/
│   ├── components/       # 再利用可能な shadcn/ui コンポーネント
│   │   ├── dashboard/    # 統計カード、システムヘルス
│   │   ├── pipeline/     # フロー実行用のデータテーブル
│   │   ├── llm/          # チャットインターフェースコンポーネント
│   │   └── ui/           # 基本的な shadcn/ui プリミティブ
│   ├── hooks/            # API 取得用のカスタムフック
│   ├── lib/              # ユーティリティ (cn, フォーマッタ)
│   ├── pages/            # ページレベルのコンポーネント
│   ├── App.tsx           # レイアウトとルーティング
│   └── main.tsx
├── tailwind.config.js
└── vite.config.ts
```

## 主要コンポーネント詳細

### 1. ダッシュボード (Home)
- **StatsGrid**: スキャン済み、処理中、アーカイブ済み、レビュー待ちのカウントを表示する4つのカード。
- **SystemHealth**: S3、Prefect、LLM の接続状況を示すインジケーター。

### 2. パイプラインテーブル
- 5秒ごとの自動ポーリング機能を備えた `shadcn/ui` テーブル。
- **バッジマッピング**: Prefect の状態を色付きバッジにマッピング。
- **App ID リンク**: クリックすると LLM ログのフィルタリングやアーカイブ詳細を表示可能。

### 3. LLM チャットビューアー
- **ChatWindow**: 「System」「User」「Assistant」の吹き出しを表示するスクロール可能なエリア。
- **Markdown レンダリング**: AI の回答のフォーマット表示をサポート。
- **言語サポート**: `Noto Sans JP` フォントスタックを使用して、日本語文字が完璧にレンダリングされることを保証。

## ローカライゼーション & 多言語対応 (i18n)
- **文字化けゼロ方針**: 表示されるすべてのデータは UTF-8 として扱われます。日本語文字列の手動エスケープは行いません。
- **フォント優先順位**: `Inter, "Noto Sans JP", sans-serif`。
- **UI ラベル**: 初期バージョンでは UI ラベルは英語とし、メタデータ（アルバム名、チャットログ）は設定された言語（日本語）で表示されます。

## ビルド & デプロイ
1. Vite がプロジェクトを `ui/frontend/dist/` にビルド。
2. FastAPI (`ui/src/ui/main.py`) が `dist` ディレクトリをマウントして SPA を配信。
3. `ui` の Dockerfile を、Node.js ビルドステージを含むマルチステージビルドに更新。

## 実装ステップ (Phase 4)
1. `ui/frontend` で Vite プロジェクトを初期化。
2. Tailwind CSS をインストールし、shadcn/ui を初期化。
3. サイドバーを備えた基本レイアウトを実装。
4. TanStack Query を使用した API クライアントレイヤーを作成。
5. ダッシュボードから順に各ページを構築。
