# CLI 再構築計画

SSTは、Webベースのダッシュボードから、強力でインタラクティブなコマンドラインインターフェース（CLI）に移行します。これにより、エッジ処理の効率を最大化し、別途UIコンテナを起動する手間を排除します。

## 1. ビジョン: "Rich Edge CLI"
新しいCLIは `Rich` ライブラリを使用し、以下のようなモダンなターミナル体験を提供します：
- **ライブ進捗**: スキャン、LLM統合、音声変換を同時に表示するマルチトラック進行状況バー。
- **対話型承認**: `--interactive` フラグにより、タグ書き込み前にターミナル上でメタデータを確認・修正できる機能。
- **集約テーブル**: 処理結果（Success/Review/Fail）を整理されたテーブル形式で表示。

## 2. コマンド構造（計画）

### `scout run`（メインパイプライン）
- `--interactive`: LLM統合後にユーザーの入力を待機。
- `--limit N`: N個のアルバムのみを処理。
- `--force`: ローカルDBを無視して再処理。

### `scout review`（レビューキュー管理）
- `list`: `output/review/` ディレクトリ内の全アルバムを表示。
- `inspect <AppID>`: 特定のアルバムのLLMログと生メタデータをターミナル上に表示。
- `approve <AppID>`: 手動タグ付け後、アルバムを `review/` から `archive/` に移動。

### `scout log`
- 直近N件の処理ログを表示。
- 実行中のプロセスからライブログをストリーム表示。

## 3. UIからCLIへのマッピング（移行）

| Web UI 機能 | CLI での代替 |
| :--- | :--- |
| ダッシュボード アルバムリスト | `scout review list` / 実行後のサマリーテーブル |
| メタデータ・インスペクター | `scout review inspect` (Richテーブル/JSON出力) |
| LLMログ表示 | `scout review inspect` (Markdown出力) |
| 再処理ボタン | `scout run --force --app-id <ID>` |
| 一括削除 | 標準のシェルコマンド (`rm -rf output/review/*`) |

## 4. 技術タスク

### UX/UI
- [ ] `LocalProcessor` のループに `rich.progress` を実装。
- [ ] 最終サマリーに `rich.table` を実装。
- [ ] メタデータの対話型承認のためにCLIプロンプト（`rich.console` または `questionary`）を追加。

### ロジック
- [ ] `main.py` をリファクタリングし、`click` または `typer` を使用して高度なコマンド引数処理を実装。
- [ ] SQLiteデータベースを拡張し、「手動レビュー済み」ステータスをより正確に追跡。
- [ ] 長いLLMログをターミナルで閲覧するための簡易ページャーの実装。
